from django.contrib import admin

from .models import AppSettings, ExtractionAttempt, Recipe, RecipeIngredient, RecipeSource


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 0


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    list_display = ("lm_studio_base_url", "lm_studio_model", "transcript_limit", "updated_at")

    def has_add_permission(self, request):
        return not AppSettings.objects.exists()


@admin.register(RecipeSource)
class RecipeSourceAdmin(admin.ModelAdmin):
    list_display = ("title", "channel", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "channel", "url", "video_id")


@admin.register(ExtractionAttempt)
class ExtractionAttemptAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "lm_studio_model", "prompt_version", "started_at")
    list_filter = ("status", "prompt_version", "started_at")
    search_fields = ("source__title", "source__url", "lm_studio_model", "error_details")


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("title", "servings", "total_time", "confidence", "created_at")
    search_fields = ("title", "summary")
    inlines = [RecipeIngredientInline]
