from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from recipes.models import Recipe, RecipeSource


@dataclass(frozen=True)
class DuplicateCandidate:
    recipe: Recipe
    score: float
    reasons: list[str]


def find_duplicate_video_recipe(video_id: str, source_id: int | None = None) -> Recipe | None:
    if not video_id:
        return None

    sources = RecipeSource.objects.filter(
        video_id=video_id,
        status=RecipeSource.Status.DONE,
        recipe__isnull=False,
    ).select_related("recipe")
    if source_id:
        sources = sources.exclude(pk=source_id)

    source = sources.order_by("created_at").first()
    return source.recipe if source else None


def find_similar_recipes(recipe: Recipe, limit: int = 5) -> list[DuplicateCandidate]:
    recipe = (
        Recipe.objects.prefetch_related("ingredient_items")
        .select_related("source")
        .get(pk=recipe.pk)
    )
    recipe_title = _normalize_text(recipe.title)
    recipe_ingredients = _ingredient_tokens(recipe)
    candidates = []

    for other in (
        Recipe.objects.exclude(pk=recipe.pk)
        .select_related("source")
        .prefetch_related("ingredient_items")
    ):
        title_score = _title_similarity(recipe_title, _normalize_text(other.title))
        ingredient_score = _ingredient_similarity(recipe_ingredients, _ingredient_tokens(other))
        reasons = _candidate_reasons(title_score, ingredient_score)
        if reasons:
            candidates.append(
                DuplicateCandidate(
                    recipe=other,
                    score=max(title_score, ingredient_score),
                    reasons=reasons,
                )
            )

    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[:limit]


def _candidate_reasons(title_score: float, ingredient_score: float) -> list[str]:
    reasons = []
    if title_score >= 0.82:
        reasons.append(f"ähnlicher Titel ({title_score:.0%})")
    if ingredient_score >= 0.68:
        reasons.append(f"sehr ähnliche Zutaten ({ingredient_score:.0%})")
    return reasons


def _title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _ingredient_similarity(left: set[str], right: set[str]) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    return len(left & right) / len(left | right)


def _ingredient_tokens(recipe: Recipe) -> set[str]:
    tokens = set()
    for ingredient in recipe.ingredient_payloads():
        if isinstance(ingredient, dict):
            tokens.update(_tokenize(ingredient.get("name", "")))
        else:
            tokens.update(_tokenize(str(ingredient)))
    return tokens


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(_tokenize(ascii_text))


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]+", value.lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


_STOPWORDS = {
    "and",
    "auf",
    "aus",
    "das",
    "der",
    "die",
    "ein",
    "eine",
    "einer",
    "for",
    "mit",
    "oder",
    "the",
    "und",
    "von",
}
