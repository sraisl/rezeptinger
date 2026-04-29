from __future__ import annotations

import re
from typing import Any

from django.db import OperationalError, connection
from django.db.models import Case, IntegerField, QuerySet, Value, When

from recipes.models import Recipe


def search_recipes(query: str) -> QuerySet[Recipe]:
    recipe_ids = matching_recipe_ids(query)
    if not recipe_ids:
        return Recipe.objects.none()

    ordering = Case(
        *[When(pk=recipe_id, then=Value(index)) for index, recipe_id in enumerate(recipe_ids)],
        output_field=IntegerField(),
    )
    return Recipe.objects.select_related("source").filter(pk__in=recipe_ids).order_by(ordering)


def matching_recipe_ids(query: str) -> list[int]:
    match_query = fts_query(query)
    if not match_query:
        return []

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT recipe_id
                FROM recipes_recipe_fts
                WHERE recipes_recipe_fts MATCH %s
                ORDER BY rank
                """,
                [match_query],
            )
            return [row[0] for row in cursor.fetchall()]
    except OperationalError:
        return []


def sync_recipe_search_index(recipe: Recipe) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM recipes_recipe_fts WHERE recipe_id = %s", [recipe.pk])
            cursor.execute(
                """
                INSERT INTO recipes_recipe_fts(
                    recipe_id, title, ingredients, steps, channel, transcript
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    recipe.pk,
                    recipe.title,
                    ingredients_text(recipe.ingredients),
                    list_text(recipe.steps),
                    recipe.source.channel,
                    recipe.source.transcript,
                ],
            )
    except OperationalError:
        return


def delete_recipe_search_index(recipe_id: int) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM recipes_recipe_fts WHERE recipe_id = %s", [recipe_id])
    except OperationalError:
        return


def fts_query(query: str) -> str:
    tokens = re.findall(r"[\w]+", query, flags=re.UNICODE)
    return " ".join(f"{token}*" for token in tokens)


def ingredients_text(ingredients: list[Any]) -> str:
    parts = []
    for ingredient in ingredients or []:
        if isinstance(ingredient, dict):
            parts.extend(
                str(ingredient.get(key, ""))
                for key in ("quantity", "unit", "name", "note")
                if ingredient.get(key)
            )
        else:
            parts.append(str(ingredient))
    return " ".join(parts)


def list_text(values: list[Any]) -> str:
    return " ".join(str(value) for value in values or [])
