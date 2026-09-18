from django import forms

from .models import Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task

        fields = [
            "title",
            "priority",
            "estimated_time",
        ]

        labels = {
            "estimated_time": "Estimated Time (minutes)",
        }

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Enter task title",
                    "class": "form-control",
                }
            ),
            "priority": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "estimated_time": forms.NumberInput(
                attrs={
                    "min": 1,
                    "placeholder": "Minutes",
                    "class": "form-control",
                }
            ),
        }

    def clean_title(self):
        title = self.cleaned_data["title"].strip()

        if not title:
            raise forms.ValidationError(
                "Task title cannot be empty."
            )

        return title

    def clean_estimated_time(self):
        estimated_time = self.cleaned_data[
            "estimated_time"
        ]

        if estimated_time <= 0:
            raise forms.ValidationError(
                "Estimated time must be greater than zero."
            )

        return estimated_time