from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import httpx


class WebpageUnavailable(Exception):
    pass


@dataclass(frozen=True)
class WebpageRecipe:
    url: str
    title: str
    site_name: str
    text: str


def fetch_webpage_recipe(url: str) -> WebpageRecipe:
    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=15,
            headers={"User-Agent": "Rezeptinger/0.1 (+local recipe extractor)"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise WebpageUnavailable(f"Webseite konnte nicht gelesen werden: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise WebpageUnavailable("Die URL liefert keine HTML-Webseite.")

    parser = _RecipePageParser()
    parser.feed(response.text)
    parser.close()

    title = _first_non_empty(parser.recipe_titles, parser.title, response.url.host or "Webseite")
    site_name = _first_non_empty(parser.site_names, response.url.host or "Webseite")
    text = _combined_recipe_text(parser.structured_recipes, parser.visible_text)
    if len(text) < 40:
        raise WebpageUnavailable(
            "Auf der Webseite wurde zu wenig verwertbarer Rezepttext gefunden."
        )

    return WebpageRecipe(
        url=str(response.url),
        title=title[:255],
        site_name=site_name[:255],
        text=text,
    )


def _combined_recipe_text(structured_recipes: list[dict[str, Any]], visible_text: str) -> str:
    chunks = []
    for recipe in structured_recipes:
        chunks.extend(_recipe_chunks(recipe))
    if not chunks:
        chunks.append(visible_text)
    text = "\n\n".join(chunk for chunk in chunks if chunk)
    return text[:60000]


def _recipe_chunks(recipe: dict[str, Any]) -> list[str]:
    chunks = []
    for key, label in (
        ("name", "Titel"),
        ("description", "Beschreibung"),
        ("recipeYield", "Portionen"),
        ("prepTime", "Vorbereitung"),
        ("cookTime", "Kochen/Backen"),
        ("totalTime", "Gesamtzeit"),
    ):
        value = _string_value(recipe.get(key))
        if value:
            chunks.append(f"{label}: {value}")

    ingredients = _list_strings(recipe.get("recipeIngredient"))
    if ingredients:
        chunks.append("Zutaten:\n" + "\n".join(f"- {ingredient}" for ingredient in ingredients))

    instructions = _instruction_strings(recipe.get("recipeInstructions"))
    if instructions:
        numbered_steps = (
            f"{index}. {step}" for index, step in enumerate(instructions, 1)
        )
        chunks.append("Zubereitung:\n" + "\n".join(numbered_steps))

    return chunks


def _instruction_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        steps = []
        for item in value:
            if isinstance(item, str) and item.strip():
                steps.append(item.strip())
            elif isinstance(item, dict):
                text = _string_value(item.get("text") or item.get("name"))
                if text:
                    steps.append(text)
                steps.extend(_instruction_strings(item.get("itemListElement")))
        return steps
    if isinstance(value, dict):
        return _instruction_strings(value.get("itemListElement") or value.get("text"))
    return []


def _list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _string_value(item))]


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _compact_whitespace(value)
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            for item in value:
                text = _string_value(item)
                if text:
                    return text
            continue
        text = _string_value(value)
        if text:
            return text
    return ""


def _compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class _RecipePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.site_names: list[str] = []
        self.recipe_titles: list[str] = []
        self.structured_recipes: list[dict[str, Any]] = []
        self._visible_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._ignored_stack: list[bool] = []
        self._capture_title = False
        self._capture_json_ld = False
        self._json_ld_parts: list[str] = []

    @property
    def visible_text(self) -> str:
        return "\n".join(_compact_whitespace(part) for part in self._visible_parts if part.strip())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        attr_map = {name.lower(): value or "" for name, value in attrs}
        inherited_ignore = self._ignored_stack[-1] if self._ignored_stack else False
        self._ignored_stack.append(inherited_ignore or _is_noise_element(tag, attr_map))
        if tag == "title":
            self._capture_title = True
        elif tag == "script" and attr_map.get("type", "").lower() == "application/ld+json":
            self._capture_json_ld = True
            self._json_ld_parts = []
        elif tag == "meta":
            self._capture_meta(attr_map)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._capture_title = False
        elif tag == "script" and self._capture_json_ld:
            self._capture_json_ld = False
            self._capture_json_ld_payload("".join(self._json_ld_parts))
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
            self._ignored_stack.pop()
        elif tag in self._tag_stack:
            index = self._tag_stack.index(tag)
            self._tag_stack.pop(index)
            self._ignored_stack.pop(index)

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self.title = _compact_whitespace(f"{self.title} {data}")
        elif self._capture_json_ld:
            self._json_ld_parts.append(data)
        elif not any(self._ignored_stack):
            text = _compact_whitespace(data)
            if len(text) >= 2 and not _is_noise_text(text):
                self._visible_parts.append(text)

    def _capture_meta(self, attrs: dict[str, str]) -> None:
        key = attrs.get("property") or attrs.get("name")
        content = attrs.get("content", "")
        if not key or not content:
            return
        key = key.lower()
        if key in {"og:title", "twitter:title"}:
            self.recipe_titles.append(content)
        elif key in {"og:site_name", "application-name"}:
            self.site_names.append(content)

    def _capture_json_ld_payload(self, raw_payload: str) -> None:
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return
        for item in _flatten_json_ld(payload):
            if _is_recipe_schema(item):
                self.structured_recipes.append(item)
                title = _string_value(item.get("name"))
                if title:
                    self.recipe_titles.append(title)


def _flatten_json_ld(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = []
        for item in payload:
            items.extend(_flatten_json_ld(item))
        return items
    if not isinstance(payload, dict):
        return []

    items = [payload]
    graph = payload.get("@graph")
    if isinstance(graph, list):
        items.extend(item for item in graph if isinstance(item, dict))
    return items


def _is_recipe_schema(item: dict[str, Any]) -> bool:
    item_type = item.get("@type")
    if isinstance(item_type, str):
        return item_type.lower() == "recipe"
    if isinstance(item_type, list):
        return any(str(value).lower() == "recipe" for value in item_type)
    return False


def _is_noise_element(tag: str, attrs: dict[str, str]) -> bool:
    if tag in _NOISE_TAGS:
        return True
    role = attrs.get("role", "").lower()
    if role in _NOISE_ROLES:
        return True
    marker = " ".join(
        attrs.get(name, "").lower()
        for name in ("id", "class", "aria-label", "data-testid")
    )
    return any(pattern.search(marker) for pattern in _NOISE_ATTRIBUTE_PATTERNS)


def _is_noise_text(text: str) -> bool:
    normalized = text.lower()
    return any(pattern.search(normalized) for pattern in _NOISE_TEXT_PATTERNS)


_NOISE_TAGS = {
    "aside",
    "button",
    "footer",
    "form",
    "iframe",
    "nav",
    "noscript",
    "script",
    "select",
    "style",
    "svg",
}

_NOISE_ROLES = {
    "banner",
    "complementary",
    "contentinfo",
    "navigation",
    "search",
}

_NOISE_ATTRIBUTE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"\bad(s|vert|vertisement)?\b",
        r"\bcomment(s)?\b",
        r"\bconsent\b",
        r"\bcookie(s)?\b",
        r"\bfooter\b",
        r"\bheader\b",
        r"\bnewsletter\b",
        r"\bpromo\b",
        r"\bshare\b",
        r"\bsocial\b",
    )
]

_NOISE_TEXT_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"alle cookies akzeptieren",
        r"cookie[- ]?einstellungen",
        r"datenschutzerkl[aä]rung",
        r"newsletter abonnieren",
        r"subscribe to our newsletter",
    )
]
