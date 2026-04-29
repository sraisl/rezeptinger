from django import forms

from .models import RecipeSource


class RecipeSourceForm(forms.ModelForm):
    class Meta:
        model = RecipeSource
        fields = ["url"]
        labels = {"url": "YouTube URL"}
        widgets = {
            "url": forms.URLInput(
                attrs={
                    "placeholder": "https://www.youtube.com/watch?v=...",
                    "autofocus": True,
                }
            )
        }
