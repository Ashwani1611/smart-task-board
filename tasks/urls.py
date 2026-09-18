from django.urls import path

from . import views


app_name = "tasks"


urlpatterns = [
    path(
        "",
        views.task_board,
        name="board",
    ),
    path(
        "tasks/<int:task_id>/complete/",
        views.task_complete,
        name="complete",
    ),
]