from django import forms

from .models import Recipe, RecipeSource, Tag
from .services.ingredients import replace_recipe_ingredients


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


class RecipeEditForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        label="Tags",
        queryset=Tag.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    ingredients_text = forms.CharField(
        label="Zutaten",
        required=False,
        widget=forms.Textarea(attrs={"rows": 10}),
    )
    steps_text = forms.CharField(
        label="Zubereitung",
        required=False,
        widget=forms.Textarea(attrs={"rows": 10}),
    )
    notes_text = forms.CharField(
        label="Notizen",
        required=False,
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    class Meta:
        model = Recipe
        fields = [
            "title",
            "summary",
            "servings",
            "prep_time",
            "cook_time",
            "total_time",
            "tags",
        ]
        labels = {
            "title": "Titel",
            "summary": "Kurzbeschreibung",
            "servings": "Portionen",
            "prep_time": "Vorbereitung",
            "cook_time": "Kochen/Backen",
            "total_time": "Gesamtzeit",
            "tags": "Tags",
        }
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags"].queryset = Tag.objects.all()
        if self.instance and self.instance.pk:
            self.fields["tags"].initial = self.instance.tags.all()
            self.fields["ingredients_text"].initial = ingredients_to_text(
                self.instance.ingredient_payloads()
            )
            self.fields["steps_text"].initial = lines_to_text(self.instance.steps)
            self.fields["notes_text"].initial = lines_to_text(self.instance.notes)

    def save(self, commit=True):
        recipe = super().save(commit=False)
        ingredients = text_to_ingredients(self.cleaned_data["ingredients_text"])
        recipe.ingredients = ingredients
        recipe.steps = text_to_lines(self.cleaned_data["steps_text"])
        recipe.notes = text_to_lines(self.cleaned_data["notes_text"])
        if commit:
            recipe.save()
            self.save_m2m()
            replace_recipe_ingredients(recipe, ingredients)
        return recipe


def ingredients_to_text(ingredients: list) -> str:
    lines = []
    for ingredient in ingredients:
        if isinstance(ingredient, dict):
            parts = [
                str(ingredient.get("quantity", "")).strip(),
                str(ingredient.get("unit", "")).strip(),
                str(ingredient.get("name", "")).strip(),
            ]
            line = " ".join(part for part in parts if part)
            note = str(ingredient.get("note", "")).strip()
            lines.append(f"{line} ({note})" if note else line)
        else:
            lines.append(str(ingredient))
    return "\n".join(line for line in lines if line)


def lines_to_text(values: list) -> str:
    return "\n".join(str(value) for value in values if str(value).strip())


def text_to_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def text_to_ingredients(value: str) -> list[dict[str, str]]:
    ingredients = []
    for line in text_to_lines(value):
        ingredients.append({"quantity": "", "unit": "", "name": line, "note": ""})
    return ingredients
