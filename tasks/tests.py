import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from .models import Task
from .services import (
    HINT_ALREADY_COMPLETED,
    HINT_HIDDEN,
    HINT_LOCKED,
    HINT_PRIORITY,
    HINT_TIME,
    LOCK_DURATION_MINUTES,
    complete_task,
    completion_window_valid,
    create_task,
    hidden_rule_allows_completion,
    high_priority_requirement_met,
    is_odd_minute_task,
)


IST = ZoneInfo("Asia/Kolkata")


class TaskFactoryMixin:
    def dt(self, *, hour=10, minute=30, second=0):
        return datetime(
            2026,
            9,
            18,
            hour,
            minute,
            second,
            tzinfo=IST,
        )

    def make_task(
        self,
        *,
        title="Test task",
        priority=Task.Priority.MEDIUM,
        estimated_time=10,
        created_at=None,
        completed_at=None,
        locked_until=None,
    ):
        task = Task.objects.create(
            title=title,
            priority=priority,
            estimated_time=estimated_time,
        )

        updates = {}

        if created_at is not None:
            updates["created_at"] = created_at

        if completed_at is not None:
            updates["completed_at"] = completed_at

        if locked_until is not None:
            updates["locked_until"] = locked_until

        if updates:
            Task.objects.filter(pk=task.pk).update(**updates)
            task.refresh_from_db()

        return task

    def make_hidden_task(
        self,
        *,
        allowed,
        priority=Task.Priority.MEDIUM,
        estimated_time=10,
        created_at=None,
    ):
        task = self.make_task(
            title="Hidden-rule seed",
            priority=priority,
            estimated_time=estimated_time,
            created_at=created_at or self.dt(minute=30),
        )

        for index in range(1000):
            task.title = f"hidden-{allowed}-{index}"
            task.save(update_fields=["title"])

            if hidden_rule_allows_completion(task) is allowed:
                return task

        self.fail("Could not find a deterministic hidden-rule test title.")


class HighPriorityRuleTests(TaskFactoryMixin, TestCase):
    def test_low_priority_does_not_require_completed_low_task(self):
        task = self.make_task(priority=Task.Priority.LOW)

        self.assertTrue(high_priority_requirement_met(task))

    def test_medium_priority_does_not_require_completed_low_task(self):
        task = self.make_task(priority=Task.Priority.MEDIUM)

        self.assertTrue(high_priority_requirement_met(task))

    def test_high_priority_fails_without_completed_low_task(self):
        task = self.make_task(priority=Task.Priority.HIGH)

        self.assertFalse(high_priority_requirement_met(task))

    def test_pending_low_task_does_not_unlock_high_priority(self):
        self.make_task(priority=Task.Priority.LOW)
        high = self.make_task(priority=Task.Priority.HIGH)

        self.assertFalse(high_priority_requirement_met(high))

    def test_completed_low_task_unlocks_high_priority(self):
        self.make_task(
            priority=Task.Priority.LOW,
            completed_at=self.dt(hour=9),
        )
        high = self.make_task(priority=Task.Priority.HIGH)

        self.assertTrue(high_priority_requirement_met(high))

    def test_complete_high_priority_returns_cryptic_hint_when_blocked(self):
        high = self.make_hidden_task(
            allowed=True,
            priority=Task.Priority.HIGH,
            created_at=self.dt(minute=30),
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=self.dt(minute=31),
        ):
            result = complete_task(high)

        self.assertFalse(result.success)
        self.assertEqual(result.hint, HINT_PRIORITY)

    def test_complete_high_priority_succeeds_after_low_is_completed(self):
        self.make_task(
            priority=Task.Priority.LOW,
            completed_at=self.dt(hour=9),
        )
        high = self.make_hidden_task(
            allowed=True,
            priority=Task.Priority.HIGH,
            created_at=self.dt(minute=30),
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=self.dt(minute=31),
        ):
            result = complete_task(high)

        high.refresh_from_db()

        self.assertTrue(result.success)
        self.assertIsNotNone(high.completed_at)


class RapidCreationLockTests(TaskFactoryMixin, TestCase):
    def test_first_three_tasks_are_unlocked(self):
        now = self.dt(minute=30)

        with patch("tasks.services.timezone.now", return_value=now):
            tasks = [
                create_task(
                    title=f"Task {index}",
                    priority=Task.Priority.LOW,
                    estimated_time=10,
                )
                for index in range(1, 4)
            ]

            self.assertTrue(all(not task.is_locked for task in tasks))

    def test_fourth_task_is_locked(self):
        now = self.dt(minute=30)

        with patch("tasks.services.timezone.now", return_value=now):
            for index in range(3):
                create_task(
                    title=f"Task {index}",
                    priority=Task.Priority.LOW,
                    estimated_time=10,
                )

            fourth = create_task(
                title="Fourth task",
                priority=Task.Priority.LOW,
                estimated_time=10,
            )

            self.assertTrue(fourth.is_locked)

    def test_locked_until_is_five_minutes_after_creation(self):
        now = self.dt(minute=30)

        with patch("tasks.services.timezone.now", return_value=now):
            for index in range(3):
                create_task(
                    title=f"Task {index}",
                    priority=Task.Priority.LOW,
                    estimated_time=10,
                )

            fourth = create_task(
                title="Fourth task",
                priority=Task.Priority.LOW,
                estimated_time=10,
            )

        self.assertEqual(
            fourth.locked_until,
            now + timedelta(minutes=LOCK_DURATION_MINUTES),
        )

    def test_locked_task_cannot_be_completed(self):
        now = self.dt(minute=30)

        task = self.make_hidden_task(
            allowed=True,
            created_at=now,
        )
        Task.objects.filter(pk=task.pk).update(
            locked_until=now + timedelta(minutes=5)
        )
        task.refresh_from_db()

        with patch("tasks.services.timezone.now", return_value=now):
            result = complete_task(task)

        self.assertFalse(result.success)
        self.assertEqual(result.hint, HINT_LOCKED)

    def test_is_locked_false_without_lock_timestamp(self):
        task = self.make_task()

        self.assertFalse(task.is_locked)

    def test_is_locked_true_before_expiry(self):
        now = self.dt(minute=30)
        task = self.make_task(
            locked_until=now + timedelta(minutes=5),
        )

        with patch("tasks.models.timezone.now", return_value=now):
            self.assertTrue(task.is_locked)

    def test_is_locked_false_at_expiry(self):
        now = self.dt(minute=30)
        task = self.make_task(locked_until=now)

        with patch("tasks.models.timezone.now", return_value=now):
            self.assertFalse(task.is_locked)


class OddMinuteWindowTests(TaskFactoryMixin, TestCase):
    def test_even_minute_task_is_not_odd(self):
        task = self.make_task(created_at=self.dt(minute=30))

        self.assertFalse(is_odd_minute_task(task))

    def test_odd_minute_task_is_detected(self):
        task = self.make_task(created_at=self.dt(minute=31))

        self.assertTrue(is_odd_minute_task(task))

    def test_even_minute_task_has_no_completion_deadline(self):
        task = self.make_task(
            estimated_time=1,
            created_at=self.dt(minute=30),
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=self.dt(hour=12, minute=30),
        ):
            self.assertTrue(completion_window_valid(task))

    def test_odd_minute_task_is_valid_inside_window(self):
        created = self.dt(minute=31)
        task = self.make_task(
            estimated_time=10,
            created_at=created,
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=created + timedelta(minutes=9),
        ):
            self.assertTrue(completion_window_valid(task))

    def test_odd_minute_task_is_valid_exactly_at_deadline(self):
        created = self.dt(minute=31)
        task = self.make_task(
            estimated_time=10,
            created_at=created,
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=created + timedelta(minutes=10),
        ):
            self.assertTrue(completion_window_valid(task))

    def test_odd_minute_task_fails_after_deadline(self):
        created = self.dt(minute=31)
        task = self.make_task(
            estimated_time=10,
            created_at=created,
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=created + timedelta(minutes=10, seconds=1),
        ):
            self.assertFalse(completion_window_valid(task))

    def test_complete_expired_odd_minute_task_returns_time_hint(self):
        created = self.dt(minute=31)
        task = self.make_hidden_task(
            allowed=True,
            estimated_time=10,
            created_at=created,
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=created + timedelta(minutes=11),
        ):
            result = complete_task(task)

        self.assertFalse(result.success)
        self.assertEqual(result.hint, HINT_TIME)


class HiddenRuleTests(TaskFactoryMixin, TestCase):
    def test_hidden_rule_is_deterministic(self):
        task = self.make_task(
            title="Deterministic",
            estimated_time=17,
        )

        first = hidden_rule_allows_completion(task)
        second = hidden_rule_allows_completion(task)

        self.assertEqual(first, second)

    def test_hidden_rule_matches_sha256_contract(self):
        task = self.make_task(
            title="Hash contract",
            estimated_time=23,
        )
        value = f"{task.pk}:{task.title}:{task.estimated_time}"
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        expected = int(digest[:8], 16) % 5 != 0

        self.assertEqual(
            hidden_rule_allows_completion(task),
            expected,
        )

    def test_helper_finds_real_database_task_that_passes_hidden_rule(self):
        task = self.make_hidden_task(allowed=True)

        self.assertTrue(hidden_rule_allows_completion(task))

    def test_helper_finds_real_database_task_that_fails_hidden_rule(self):
        task = self.make_hidden_task(allowed=False)

        self.assertFalse(hidden_rule_allows_completion(task))

    def test_hidden_rule_block_returns_cryptic_hint(self):
        task = self.make_hidden_task(
            allowed=False,
            created_at=self.dt(minute=30),
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=self.dt(minute=31),
        ):
            result = complete_task(task)

        self.assertFalse(result.success)
        self.assertEqual(result.hint, HINT_HIDDEN)


class TaskModelTests(TaskFactoryMixin, TestCase):
    def test_pending_status(self):
        task = self.make_task()

        self.assertEqual(task.status, "Pending")

    def test_locked_status(self):
        now = self.dt(minute=30)
        task = self.make_task(
            locked_until=now + timedelta(minutes=5),
        )

        with patch("tasks.models.timezone.now", return_value=now):
            self.assertEqual(task.status, "Locked")

    def test_completed_status_takes_precedence_over_lock(self):
        now = self.dt(minute=30)
        task = self.make_task(
            completed_at=now,
            locked_until=now + timedelta(minutes=5),
        )

        with patch("tasks.models.timezone.now", return_value=now):
            self.assertEqual(task.status, "Completed")

    def test_is_completed_property(self):
        task = self.make_task()

        self.assertFalse(task.is_completed)

        Task.objects.filter(pk=task.pk).update(
            completed_at=self.dt(minute=31)
        )
        task.refresh_from_db()

        self.assertTrue(task.is_completed)

    def test_string_representation_is_title(self):
        task = self.make_task(title="Write tests")

        self.assertEqual(str(task), "Write tests")


class CompletionGuardTests(TaskFactoryMixin, TestCase):
    def test_already_completed_task_is_rejected(self):
        completed_at = self.dt(minute=30)
        task = self.make_task(
            completed_at=completed_at,
            created_at=self.dt(minute=28),
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=self.dt(minute=31),
        ):
            result = complete_task(task)

        self.assertFalse(result.success)
        self.assertEqual(result.hint, HINT_ALREADY_COMPLETED)


class TaskBoardViewTests(TaskFactoryMixin, TestCase):
    def test_get_board_renders_template(self):
        response = self.client.get(reverse("tasks:board"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tasks/board.html")

    def test_post_board_creates_task(self):
        response = self.client.post(
            reverse("tasks:board"),
            {
                "title": "Create from view",
                "priority": Task.Priority.MEDIUM,
                "estimated_time": 15,
            },
        )

        self.assertRedirects(response, reverse("tasks:board"))
        self.assertTrue(
            Task.objects.filter(title="Create from view").exists()
        )

    def test_invalid_form_renders_errors_without_creating_task(self):
        response = self.client.post(
            reverse("tasks:board"),
            {
                "title": "Invalid estimate",
                "priority": Task.Priority.LOW,
                "estimated_time": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.count(), 0)
        self.assertContains(
            response,
            "Estimated time must be greater than zero.",
        )

    def test_complete_view_completes_eligible_task(self):
        task = self.make_hidden_task(
            allowed=True,
            created_at=self.dt(minute=30),
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=self.dt(minute=31),
        ):
            response = self.client.post(
                reverse("tasks:complete", args=[task.pk])
            )

        task.refresh_from_db()

        self.assertRedirects(response, reverse("tasks:board"))
        self.assertIsNotNone(task.completed_at)

    def test_complete_view_shows_failure_hint(self):
        task = self.make_hidden_task(
            allowed=True,
            priority=Task.Priority.HIGH,
            created_at=self.dt(minute=30),
        )

        with patch(
            "tasks.services.timezone.now",
            return_value=self.dt(minute=31),
        ):
            response = self.client.post(
                reverse("tasks:complete", args=[task.pk]),
                follow=True,
            )

        self.assertContains(response, HINT_PRIORITY)

    def test_complete_view_returns_404_for_missing_task(self):
        response = self.client.post(
            reverse("tasks:complete", args=[999999])
        )

        self.assertEqual(response.status_code, 404)

    def test_get_complete_url_redirects_without_mutating_task(self):
        task = self.make_hidden_task(
            allowed=True,
            created_at=self.dt(minute=30),
        )

        response = self.client.get(
            reverse("tasks:complete", args=[task.pk])
        )
        task.refresh_from_db()

        self.assertRedirects(response, reverse("tasks:board"))
        self.assertIsNone(task.completed_at)

    def test_locked_task_renders_countdown_hook(self):
        now = self.dt(minute=30)
        task = self.make_task(
            locked_until=now + timedelta(minutes=5),
        )

        with patch("tasks.models.timezone.now", return_value=now):
            response = self.client.get(reverse("tasks:board"))

        self.assertContains(response, "lock-countdown")
        self.assertContains(response, "data-lock-until")
