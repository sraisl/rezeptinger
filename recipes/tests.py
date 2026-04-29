from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from recipes.models import Recipe, RecipeSource
from recipes.services import lmstudio
from recipes.services.extractor import process_source
from recipes.services.youtube import YouTubeVideo


class RecipeViewsTests(TestCase):
    def test_index_renders(self):
        response = self.client.get(reverse("recipes:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rezeptinger")
        self.assertContains(response, "YouTube URL")

    def test_failed_source_shows_retry_button(self):
        RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=failed",
            status=RecipeSource.Status.FAILED,
            error_message="LM Studio ist nicht erreichbar.",
        )

        response = self.client.get(reverse("recipes:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Erneut versuchen")

    def test_retry_source_enqueues_source(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=retry",
            status=RecipeSource.Status.FAILED,
            error_message="LM Studio ist nicht erreichbar.",
        )

        from unittest.mock import patch

        with patch("recipes.views.enqueue_source_processing") as enqueue:
            response = self.client.post(reverse("recipes:retry_source", kwargs={"pk": source.pk}))

        self.assertRedirects(response, reverse("recipes:source_detail", kwargs={"pk": source.pk}))
        enqueue.assert_called_once_with(source)

    def test_source_status_returns_current_status(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=status",
            status=RecipeSource.Status.PROCESSING,
        )

        response = self.client.get(reverse("recipes:source_status", kwargs={"pk": source.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], RecipeSource.Status.PROCESSING)

    def test_api_create_extraction_accepts_json(self):
        from unittest.mock import patch

        with patch("recipes.views.enqueue_source_processing") as enqueue:
            response = self.client.post(
                reverse("recipes:api_create_extraction"),
                data={"url": "https://www.youtube.com/watch?v=api"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], RecipeSource.Status.PENDING)
        self.assertIn("/api/extractions/", data["status_url"])
        enqueue.assert_called_once()

    def test_api_create_extraction_rejects_invalid_url(self):
        response = self.client.post(
            reverse("recipes:api_create_extraction"),
            data={"url": "not-a-url"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_api_status_includes_recipe_when_done(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=done",
            status=RecipeSource.Status.DONE,
        )
        Recipe.objects.create(source=source, title="API Pasta")

        response = self.client.get(
            reverse("recipes:api_extraction_status", kwargs={"pk": source.pk})
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], RecipeSource.Status.DONE)
        self.assertEqual(data["recipe"]["title"], "API Pasta")

    def test_data_export_returns_catalog_json(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=export",
            status=RecipeSource.Status.DONE,
        )
        Recipe.objects.create(source=source, title="Export Pasta")

        response = self.client.get(reverse("recipes:data_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = json_loads(response.content)
        self.assertEqual(data["format"], "rezeptinger.catalog")
        self.assertEqual(data["sources"][0]["recipe"]["title"], "Export Pasta")

    def test_data_import_creates_source_and_recipe_from_json(self):
        payload = _catalog_payload(
            url="https://www.youtube.com/watch?v=import",
            title="Import Video",
            recipe_title="Import Pasta",
        )

        response = self.client.post(
            reverse("recipes:data_import"),
            data=payload,
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported"], {"sources": 1, "recipes": 1})
        source = RecipeSource.objects.get(url="https://www.youtube.com/watch?v=import")
        self.assertEqual(source.recipe.title, "Import Pasta")

    def test_data_import_updates_existing_source_by_url(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=upsert",
            title="Alter Titel",
        )
        Recipe.objects.create(source=source, title="Altes Rezept")
        payload = _catalog_payload(
            url=source.url,
            title="Neuer Titel",
            recipe_title="Neues Rezept",
        )

        response = self.client.post(
            reverse("recipes:data_import"),
            data=payload,
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        source.refresh_from_db()
        self.assertEqual(source.title, "Neuer Titel")
        self.assertEqual(source.recipe.title, "Neues Rezept")

    def test_recipe_detail_links_to_edit_view(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=edit-link")
        recipe = Recipe.objects.create(source=source, title="Editierbares Rezept")

        response = self.client.get(recipe.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("recipes:edit", kwargs={"pk": recipe.pk}))

    def test_recipe_edit_updates_manual_fields(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=edit")
        recipe = Recipe.objects.create(
            source=source,
            title="Alter Titel",
            ingredients=[{"quantity": "200", "unit": "g", "name": "Pasta"}],
            steps=["Kochen."],
            notes=[],
        )

        response = self.client.post(
            reverse("recipes:edit", kwargs={"pk": recipe.pk}),
            data={
                "title": "Neuer Titel",
                "summary": "Manuell verbessert.",
                "servings": "2 Portionen",
                "prep_time": "5 Minuten",
                "cook_time": "15 Minuten",
                "total_time": "20 Minuten",
                "ingredients_text": "200 g Pasta\nOlivenöl",
                "steps_text": "Pasta kochen.\nAlles mischen.",
                "notes_text": "Mit Parmesan servieren.",
            },
        )

        self.assertRedirects(response, recipe.get_absolute_url())
        recipe.refresh_from_db()
        self.assertEqual(recipe.title, "Neuer Titel")
        self.assertEqual(recipe.summary, "Manuell verbessert.")
        self.assertEqual(recipe.ingredients[0]["name"], "200 g Pasta")
        self.assertEqual(recipe.steps, ["Pasta kochen.", "Alles mischen."])
        self.assertEqual(recipe.notes, ["Mit Parmesan servieren."])


class ExtractionTests(TestCase):
    def test_process_source_creates_recipe(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=test")
        video = YouTubeVideo(
            url=source.url,
            video_id="test",
            title="Pasta Video",
            channel="Test Kitchen",
            thumbnail_url="https://example.com/thumb.jpg",
            transcript="Wir kochen Pasta mit Tomaten.",
        )
        payload = {
            "is_recipe": True,
            "title": "Tomatenpasta",
            "summary": "Schnelle Pasta.",
            "servings": "2 Portionen",
            "prep_time": "5 Minuten",
            "cook_time": "15 Minuten",
            "total_time": "20 Minuten",
            "ingredients": [{"quantity": "200", "unit": "g", "name": "Pasta"}],
            "steps": ["Pasta kochen.", "Sauce mischen."],
            "notes": [],
            "confidence": 0.8,
        }

        with (
            self.settings(LM_STUDIO_MODEL="test"),
            self.subTest("patched services"),
        ):
            from unittest.mock import patch

            with (
                patch("recipes.services.extractor.fetch_video", return_value=video),
                patch("recipes.services.extractor.extract_recipe", return_value=payload),
            ):
                process_source(source)

        source.refresh_from_db()
        self.assertEqual(source.status, RecipeSource.Status.DONE)
        self.assertEqual(Recipe.objects.get(source=source).title, "Tomatenpasta")

    def test_process_source_marks_non_recipe_as_failed(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=chat")
        video = YouTubeVideo(
            url=source.url,
            video_id="chat",
            title="Kein Rezept",
            channel="Test Kitchen",
            thumbnail_url="",
            transcript="Heute reden wir nur.",
        )

        from unittest.mock import patch

        with (
            patch("recipes.services.extractor.fetch_video", return_value=video),
            patch(
                "recipes.services.extractor.extract_recipe",
                return_value={"is_recipe": False, "reason": "Kein Rezept.", "confidence": 0.2},
            ),
        ):
            process_source(source)

        source.refresh_from_db()
        self.assertEqual(source.status, RecipeSource.Status.FAILED)
        self.assertFalse(Recipe.objects.filter(source=source).exists())


class LmStudioTests(TestCase):
    def test_resolve_model_uses_first_loaded_model(self):
        from unittest.mock import patch

        response = _FakeResponse({"data": [{"id": "loaded-model"}]})

        with (
            self.settings(LM_STUDIO_MODEL=""),
            patch("recipes.services.lmstudio.httpx.get", return_value=response),
        ):
            self.assertEqual(lmstudio._resolve_model("http://localhost:1234/v1"), "loaded-model")

    def test_extract_recipe_retries_without_response_format_on_bad_request(self):
        from unittest.mock import patch

        bad_request = _FakeResponse({"error": "unsupported response_format"}, status_code=400)
        success = _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"is_recipe": false, "reason": "Kein Rezept.", "confidence": 0.4}'
                            )
                        }
                    }
                ]
            }
        )

        with (
            self.settings(LM_STUDIO_MODEL="loaded-model"),
            patch(
                "recipes.services.lmstudio.httpx.post",
                side_effect=[bad_request, success],
            ) as post,
        ):
            payload = lmstudio.extract_recipe("Titel", "Kanal", "Transkript")

        self.assertFalse(payload["is_recipe"])
        self.assertEqual(post.call_count, 2)
        self.assertNotIn("response_format", post.call_args_list[1].kwargs["json"])


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.reason_phrase = "OK" if status_code < 400 else "Bad Request"
        self.text = str(payload)

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "http://localhost:1234/v1/chat/completions")
            response = httpx.Response(
                self.status_code,
                json=self.payload,
                request=request,
            )
            raise httpx.HTTPStatusError("bad request", request=request, response=response)


def json_loads(content):
    import json

    return json.loads(content.decode("utf-8"))


def _catalog_payload(url: str, title: str, recipe_title: str) -> dict:
    timestamp = timezone.now().isoformat()
    return {
        "format": "rezeptinger.catalog",
        "version": 1,
        "sources": [
            {
                "url": url,
                "title": title,
                "channel": "Test Kitchen",
                "video_id": "abc",
                "thumbnail_url": "",
                "transcript": "Pasta kochen.",
                "status": RecipeSource.Status.DONE,
                "error_message": "",
                "created_at": timestamp,
                "updated_at": timestamp,
                "recipe": {
                    "title": recipe_title,
                    "summary": "Schnell.",
                    "servings": "2",
                    "prep_time": "",
                    "cook_time": "",
                    "total_time": "",
                    "ingredients": [{"name": "Pasta"}],
                    "steps": ["Kochen."],
                    "notes": [],
                    "confidence": 0.9,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            }
        ],
    }
