import hashlib
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Task


LOCK_WINDOW_MINUTES = 2
LOCK_DURATION_MINUTES = 5


@dataclass
class CompletionResult:
    success: bool
    hint: str | None = None


HINT_ALREADY_COMPLETED = (
    "This card has already crossed the finish line."
)

HINT_LOCKED = (
    "The board is not ready for this move yet."
)

HINT_PRIORITY = (
    "A smaller piece must move before this one."
)

HINT_TIME = (
    "The clock moved before the task did."
)

HINT_HIDDEN = (
    "Something unseen blocked the final step."
)

@transaction.atomic
def create_task(*, title, priority, estimated_time):
    now = timezone.now()

    window_start = now - timedelta(
        minutes=LOCK_WINDOW_MINUTES
    )

    recent_task_count = Task.objects.filter(
        created_at__gte=window_start,
        created_at__lte=now,
    ).count()

    should_lock = recent_task_count >= 3

    task = Task.objects.create(
        title=title,
        priority=priority,
        estimated_time=estimated_time,
        locked_until=(
            now + timedelta(
                minutes=LOCK_DURATION_MINUTES
            )
            if should_lock
            else None
        ),
    )

    return task





def high_priority_requirement_met(task):
    if task.priority != Task.Priority.HIGH:
        return True

    return Task.objects.filter(
        priority=Task.Priority.LOW,
        completed_at__isnull=False,
    ).exists()

def is_odd_minute_task(task):
    created_local = timezone.localtime(
        task.created_at
    )

    return created_local.minute % 2 != 0

def completion_window_valid(task):
    if not is_odd_minute_task(task):
        return True

    deadline = task.created_at + timedelta(
        minutes=task.estimated_time
    )

    return timezone.now() <= deadline


def hidden_rule_allows_completion(task):
    value = (
        f"{task.pk}:"
        f"{task.title}:"
        f"{task.estimated_time}"
    )

    digest = hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()

    number = int(
        digest[:8],
        16,
    )

    return number % 5 != 0


@transaction.atomic
def complete_task(task):
    task = Task.objects.select_for_update().get(
        pk=task.pk
    )

    if task.is_completed:
        return CompletionResult(
            success=False,
            hint=HINT_ALREADY_COMPLETED,
        )

    if task.is_locked:
        return CompletionResult(
            success=False,
            hint=HINT_LOCKED,
        )

    if not high_priority_requirement_met(task):
        return CompletionResult(
            success=False,
            hint=HINT_PRIORITY,
        )

    if not completion_window_valid(task):
        return CompletionResult(
            success=False,
            hint=HINT_TIME,
        )

    if not hidden_rule_allows_completion(task):
        return CompletionResult(
            success=False,
            hint=HINT_HIDDEN,
        )

    task.completed_at = timezone.now()

    task.save(
        update_fields=[
            "completed_at",
        ]
    )

    return CompletionResult(
        success=True
    )