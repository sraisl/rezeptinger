from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class AppSettings(models.Model):
    lm_studio_base_url = models.URLField(blank=True)
    lm_studio_model = models.CharField(max_length=255, blank=True)
    transcript_limit = models.PositiveIntegerField(default=30000)
    language_preference = models.CharField(max_length=40, blank=True)
    extraction_prompt = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "App settings"
        verbose_name_plural = "App settings"

    def __str__(self) -> str:
        return "Rezeptinger settings"

    @classmethod
    def load(cls) -> "AppSettings":
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class RecipeSource(models.Model):
    class SourceType(models.TextChoices):
        YOUTUBE = "youtube", "YouTube"
        TEXT = "text", "Text"

    class Status(models.TextChoices):
        PENDING = "pending", "Wartet"
        PROCESSING = "processing", "Wird verarbeitet"
        DONE = "done", "Fertig"
        FAILED = "failed", "Fehlgeschlagen"
        CANCELLED = "cancelled", "Abgebrochen"

    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.YOUTUBE,
    )
    url = models.URLField(unique=True)
    title = models.CharField(max_length=255, blank=True)
    channel = models.CharField(max_length=255, blank=True)
    video_id = models.CharField(max_length=64, blank=True, db_index=True)
    thumbnail_url = models.URLField(blank=True)
    transcript = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    queue_task_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title or self.url


class ExtractionAttempt(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Wird verarbeitet"
        DONE = "done", "Fertig"
        FAILED = "failed", "Fehlgeschlagen"
        CANCELLED = "cancelled", "Abgebrochen"

    source = models.ForeignKey(
        RecipeSource,
        on_delete=models.CASCADE,
        related_name="extraction_attempts",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    lm_studio_model = models.CharField(max_length=255, blank=True)
    prompt_version = models.CharField(max_length=40, blank=True)
    raw_lm_studio_response = models.TextField(blank=True)
    error_details = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source", "-started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.source} · {self.get_status_display()} · {self.started_at:%Y-%m-%d %H:%M}"


class Tag(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Recipe(models.Model):
    source = models.OneToOneField(RecipeSource, on_delete=models.CASCADE, related_name="recipe")
    tags = models.ManyToManyField(Tag, blank=True, related_name="recipes")
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
            models.Index(fields=["name"], name="recipes_rec_name_80a9f0_idx"),
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
