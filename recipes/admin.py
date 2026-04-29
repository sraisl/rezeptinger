from django.contrib import admin

from .models import Recipe, RecipeSource


@admin.register(RecipeSource)
class RecipeSourceAdmin(admin.ModelAdmin):
    list_display = ("title", "channel", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "channel", "url", "video_id")


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("title", "servings", "total_time", "confidence", "created_at")
    search_fields = ("title", "summary")
