from django.contrib import admin
from django.utils.html import format_html, format_html_join

from .models import AppSettings, ExtractionAttempt, Recipe, RecipeIngredient, RecipeSource, Tag
from .services.lmstudio import connection_status as lm_studio_connection_status


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 0


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    list_display = ("lm_studio_base_url", "lm_studio_model", "transcript_limit", "updated_at")
    readonly_fields = ("lm_studio_status",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "lm_studio_base_url",
                    "lm_studio_model",
                    "transcript_limit",
                    "language_preference",
                    "extraction_prompt",
                )
            },
        ),
        ("LM Studio status", {"fields": ("lm_studio_status",)}),
    )

    def has_add_permission(self, request):
        return not AppSettings.objects.exists()

    @admin.display(description="Connection and loaded models")
    def lm_studio_status(self, obj):
        status = lm_studio_connection_status(obj.lm_studio_base_url)
        if not status.is_available:
            return format_html(
                "<strong style='color: #a92727;'>Not reachable</strong><br>"
                "<code>{}</code><br>{}",
                status.base_url,
                status.error_message,
            )

        if not status.model_ids:
            return format_html(
                "<strong style='color: #a34815;'>Reachable, no loaded models</strong><br>"
                "<code>{}</code>",
                status.base_url,
            )

        return format_html(
            "<strong style='color: #164e42;'>Reachable</strong><br>"
            "<code>{}</code><ul>{}</ul>",
            status.base_url,
            format_html_join(
                "",
                "<li><code>{}</code></li>",
                ((model_id,) for model_id in status.model_ids),
            ),
        )


@admin.register(RecipeSource)
class RecipeSourceAdmin(admin.ModelAdmin):
    list_display = ("title", "source_type", "channel", "status", "created_at")
    list_filter = ("source_type", "status", "created_at")
    search_fields = ("title", "channel", "url", "video_id")


@admin.register(ExtractionAttempt)
class ExtractionAttemptAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "lm_studio_model", "prompt_version", "started_at")
    list_filter = ("status", "prompt_version", "started_at")
    search_fields = ("source__title", "source__url", "lm_studio_model", "error_details")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("title", "tag_names", "servings", "total_time", "confidence", "created_at")
    filter_horizontal = ("tags",)
    search_fields = ("title", "summary")
    inlines = [RecipeIngredientInline]

    @admin.display(description="Tags")
    def tag_names(self, obj):
        return ", ".join(obj.tags.values_list("name", flat=True))
