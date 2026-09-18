from django.db import models

# Create your models here.
from django.db import models
from django.utils import timezone


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    title = models.CharField(
        max_length=200
    )

    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
    )

    estimated_time = models.PositiveIntegerField(
        help_text="Estimated time in minutes"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    locked_until = models.DateTimeField(
        null=True,
        blank=True
    )

    @property
    def is_completed(self):
        return self.completed_at is not None

    @property
    def is_locked(self):
        if self.locked_until is None:
            return False

        return timezone.now() < self.locked_until

    @property
    def status(self):
        if self.is_completed:
            return "Completed"

        if self.is_locked:
            return "Locked"

        return "Pending"

    def __str__(self):
        return self.title