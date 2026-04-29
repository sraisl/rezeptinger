from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Recipe, RecipeIngredient, RecipeSource
from .services.search import delete_recipe_search_index, sync_recipe_search_index


@receiver(post_save, sender=Recipe)
def sync_recipe_after_save(sender, instance: Recipe, **kwargs):
    sync_recipe_search_index(instance)


@receiver(post_delete, sender=Recipe)
def delete_recipe_after_delete(sender, instance: Recipe, **kwargs):
    delete_recipe_search_index(instance.pk)


@receiver(post_save, sender=RecipeSource)
def sync_recipe_after_source_save(sender, instance: RecipeSource, **kwargs):
    if hasattr(instance, "recipe"):
        sync_recipe_search_index(instance.recipe)


@receiver(post_save, sender=RecipeIngredient)
def sync_recipe_after_ingredient_save(sender, instance: RecipeIngredient, **kwargs):
    sync_recipe_search_index(instance.recipe)


@receiver(post_delete, sender=RecipeIngredient)
def sync_recipe_after_ingredient_delete(sender, instance: RecipeIngredient, **kwargs):
    sync_recipe_search_index(instance.recipe)
