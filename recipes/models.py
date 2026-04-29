from django.db import models
from django.urls import reverse


class RecipeSource(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Wartet"
        PROCESSING = "processing", "Wird verarbeitet"
        DONE = "done", "Fertig"
        FAILED = "failed", "Fehlgeschlagen"

    url = models.URLField(unique=True)
    title = models.CharField(max_length=255, blank=True)
    channel = models.CharField(max_length=255, blank=True)
    video_id = models.CharField(max_length=64, blank=True, db_index=True)
    thumbnail_url = models.URLField(blank=True)
    transcript = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title or self.url


class Recipe(models.Model):
    source = models.OneToOneField(RecipeSource, on_delete=models.CASCADE, related_name="recipe")
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    servings = models.CharField(max_length=100, blank=True)
    prep_time = models.CharField(max_length=100, blank=True)
    cook_time = models.CharField(max_length=100, blank=True)
    total_time = models.CharField(max_length=100, blank=True)
    ingredients = models.JSONField(default=list, blank=True)
    steps = models.JSONField(default=list, blank=True)
    notes = models.JSONField(default=list, blank=True)
    confidence = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("recipes:detail", kwargs={"pk": self.pk})

    def ingredient_payloads(self) -> list[dict[str, str]]:
        if self.ingredient_items.exists():
            return [ingredient.as_payload() for ingredient in self.ingredient_items.all()]
        return self.ingredients


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredient_items")
    position = models.PositiveIntegerField(default=0)
    quantity = models.CharField(max_length=80, blank=True)
    unit = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=255)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        amount = " ".join(part for part in (self.quantity, self.unit) if part)
        return f"{amount} {self.name}".strip()

    def as_payload(self) -> dict[str, str]:
        return {
            "quantity": self.quantity,
            "unit": self.unit,
            "name": self.name,
            "note": self.note,
        }
