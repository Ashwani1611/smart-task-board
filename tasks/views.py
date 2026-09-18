from django.contrib import messages
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from .forms import TaskForm
from .models import Task
from .services import complete_task, create_task


def task_board(request):
    if request.method == "POST":
        form = TaskForm(request.POST)

        if form.is_valid():
            task = create_task(
                title=form.cleaned_data["title"],
                priority=form.cleaned_data["priority"],
                estimated_time=form.cleaned_data[
                    "estimated_time"
                ],
            )

            if task.is_locked:
                messages.warning(
                    request,
                    "Task created, but the board has temporarily locked it.",
                )
            else:
                messages.success(
                    request,
                    "Task created successfully.",
                )

            return redirect("tasks:board")

    else:
        form = TaskForm()

    tasks = Task.objects.all().order_by(
        "-created_at"
    )

    return render(
        request,
        "tasks/board.html",
        {
            "form": form,
            "tasks": tasks,
        },
    )


def task_complete(request, task_id):
    if request.method != "POST":
        return redirect("tasks:board")

    task = get_object_or_404(
        Task,
        pk=task_id,
    )

    result = complete_task(task)

    if result.success:
        messages.success(
            request,
            "Task completed successfully.",
        )
    else:
        messages.warning(
            request,
            result.hint,
        )

    return redirect("tasks:board")