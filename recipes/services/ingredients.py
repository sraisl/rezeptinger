from __future__ import annotations

from typing import Any

from recipes.models import Recipe, RecipeIngredient


def replace_recipe_ingredients(recipe: Recipe, ingredients: list[Any]) -> None:
    payloads = ingredient_payloads(ingredients)
    recipe.ingredient_items.all().delete()
    RecipeIngredient.objects.bulk_create(
        [
            RecipeIngredient(
                recipe=recipe,
                position=position,
                quantity=ingredient["quantity"],
                unit=ingredient["unit"],
                name=ingredient["name"],
                note=ingredient["note"],
            )
            for position, ingredient in enumerate(payloads)
        ]
    )
    Recipe.objects.filter(pk=recipe.pk).update(ingredients=payloads)
    recipe.ingredients = payloads

    from .search import sync_recipe_search_index

    sync_recipe_search_index(recipe)


def ingredient_payloads(value: list[Any]) -> list[dict[str, str]]:
    payloads = []
    for ingredient in value or []:
        if isinstance(ingredient, dict):
            payload = {
                "quantity": str(ingredient.get("quantity") or "").strip(),
                "unit": str(ingredient.get("unit") or "").strip(),
                "name": str(ingredient.get("name") or "").strip(),
                "note": str(ingredient.get("note") or "").strip(),
            }
            if payload["name"]:
                payloads.append(payload)
        else:
            name = str(ingredient).strip()
            if name:
                payloads.append({"quantity": "", "unit": "", "name": name, "note": ""})
    return payloads
