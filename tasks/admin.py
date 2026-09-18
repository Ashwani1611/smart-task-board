from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "priority",
        "estimated_time",
        "created_at",
        "completed_at",
        "locked_until",
    )

    list_filter = (
        "priority",
        "created_at",
    )

    search_fields = (
        "title",
    )