from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from recipes.models import (
    AppSettings,
    ExtractionAttempt,
    Recipe,
    RecipeIngredient,
    RecipeSource,
    Tag,
)
from recipes.services import lmstudio
from recipes.services.extractor import process_source
from recipes.services.lmstudio import RecipeExtractionResult
from recipes.services.portable_data import migrate_import_payload
from recipes.services.youtube import YouTubeRateLimited, YouTubeVideo, fetch_video


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

    def test_queue_status_renders_html(self):
        RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=processing",
            status=RecipeSource.Status.PROCESSING,
        )

        response = self.client.get(reverse("recipes:queue_status"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Queue Status")
        self.assertContains(response, "Quellen in Arbeit")

    def test_queue_status_returns_json(self):
        RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=failed-queue",
            status=RecipeSource.Status.FAILED,
        )

        response = self.client.get(
            reverse("recipes:queue_status"),
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("pending", data)
        self.assertEqual(data["failed_sources"], 1)

    def test_bookmarklet_page_renders_bookmarklet_link(self):
        response = self.client.get(reverse("recipes:bookmarklet"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An Rezeptinger senden")
        self.assertContains(response, "javascript:")
        self.assertContains(response, reverse("recipes:bookmarklet_capture"))

    def test_bookmarklet_capture_enqueues_youtube_url(self):
        from unittest.mock import patch

        with patch("recipes.views.enqueue_source_processing") as enqueue:
            response = self.client.get(
                reverse("recipes:bookmarklet_capture"),
                {"url": "https://www.youtube.com/watch?v=bookmark"},
            )

        source = RecipeSource.objects.get(url="https://www.youtube.com/watch?v=bookmark")
        self.assertRedirects(response, reverse("recipes:source_detail", kwargs={"pk": source.pk}))
        enqueue.assert_called_once_with(source)

    def test_bookmarklet_capture_rejects_invalid_url(self):
        from unittest.mock import patch

        with patch("recipes.views.enqueue_source_processing") as enqueue:
            response = self.client.get(
                reverse("recipes:bookmarklet_capture"),
                {"url": "https://example.com/not-youtube"},
            )

        self.assertRedirects(response, reverse("recipes:index"))
        self.assertFalse(RecipeSource.objects.exists())
        enqueue.assert_not_called()

    def test_cancel_processing_source_marks_cancelled_and_revokes_task(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=cancel",
            status=RecipeSource.Status.PROCESSING,
            queue_task_id="task-123",
        )

        from unittest.mock import patch

        with patch("recipes.views.revoke_source_task") as revoke:
            response = self.client.post(reverse("recipes:cancel_source", kwargs={"pk": source.pk}))

        self.assertRedirects(response, reverse("recipes:source_detail", kwargs={"pk": source.pk}))
        source.refresh_from_db()
        self.assertEqual(source.status, RecipeSource.Status.CANCELLED)
        self.assertEqual(source.queue_task_id, "")
        revoke.assert_called_once_with(source)

    def test_delete_failed_source_removes_it(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=delete",
            status=RecipeSource.Status.FAILED,
            queue_task_id="task-456",
        )

        from unittest.mock import patch

        with patch("recipes.views.revoke_source_task") as revoke:
            response = self.client.post(reverse("recipes:delete_source", kwargs={"pk": source.pk}))

        self.assertRedirects(response, reverse("recipes:index"))
        self.assertFalse(RecipeSource.objects.filter(pk=source.pk).exists())
        revoke.assert_called_once()
        self.assertEqual(revoke.call_args.args[0].url, source.url)

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
        recipe = Recipe.objects.create(source=source, title="Export Pasta")
        recipe.tags.add(Tag.objects.create(name="Pasta"), Tag.objects.create(name="Quick"))

        response = self.client.get(reverse("recipes:data_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = json_loads(response.content)
        self.assertEqual(data["format"], "rezeptinger.catalog")
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["sources"][0]["recipe"]["title"], "Export Pasta")
        self.assertEqual(data["sources"][0]["recipe"]["tags"], ["Pasta", "Quick"])

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

    def test_data_import_restores_recipe_tags(self):
        payload = _catalog_payload(
            url="https://www.youtube.com/watch?v=import-tags",
            title="Import Video",
            recipe_title="Import Dessert",
        )
        payload["version"] = 2
        payload["sources"][0]["recipe"]["tags"] = ["Dessert", "Quick"]

        response = self.client.post(
            reverse("recipes:data_import"),
            data=payload,
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        recipe = Recipe.objects.get(source__url="https://www.youtube.com/watch?v=import-tags")
        self.assertEqual(set(recipe.tags.values_list("name", flat=True)), {"Dessert", "Quick"})

    def test_data_import_accepts_version_one_without_tags(self):
        payload = _catalog_payload(
            url="https://www.youtube.com/watch?v=import-v1",
            title="Import Video",
            recipe_title="Import V1",
        )

        response = self.client.post(
            reverse("recipes:data_import"),
            data=payload,
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        recipe = Recipe.objects.get(source__url="https://www.youtube.com/watch?v=import-v1")
        self.assertEqual(list(recipe.tags.all()), [])

    def test_import_payload_migrates_version_one_to_current_shape(self):
        payload = _catalog_payload(
            url="https://www.youtube.com/watch?v=migrate-v1",
            title="Import Video",
            recipe_title="Import V1",
        )

        migrated = migrate_import_payload(payload)

        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["sources"][0]["recipe"]["tags"], [])

    def test_import_payload_leaves_version_two_tags_unchanged(self):
        payload = _catalog_payload(
            url="https://www.youtube.com/watch?v=migrate-v2",
            title="Import Video",
            recipe_title="Import V2",
        )
        payload["version"] = 2
        payload["sources"][0]["recipe"]["tags"] = ["Dessert"]

        migrated = migrate_import_payload(payload)

        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["sources"][0]["recipe"]["tags"], ["Dessert"])

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

    def test_data_import_rejects_invalid_format(self):
        response = self.client.post(
            reverse("recipes:data_import"),
            data={"format": "other", "version": 1, "sources": []},
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Rezeptinger-Katalogexport", response.json()["error"])

    def test_data_import_rejects_missing_version(self):
        response = self.client.post(
            reverse("recipes:data_import"),
            data={"format": "rezeptinger.catalog", "sources": []},
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Versionsnummer", response.json()["error"])

    def test_data_import_rejects_unsupported_version(self):
        response = self.client.post(
            reverse("recipes:data_import"),
            data={"format": "rezeptinger.catalog", "version": 99, "sources": []},
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("nicht unterstützt", response.json()["error"])

    def test_data_import_rejects_invalid_sources(self):
        response = self.client.post(
            reverse("recipes:data_import"),
            data={"format": "rezeptinger.catalog", "version": 2, "sources": {}},
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Quellenliste", response.json()["error"])

    def test_recipe_detail_links_to_edit_view(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=edit-link")
        recipe = Recipe.objects.create(source=source, title="Editierbares Rezept")

        response = self.client.get(recipe.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("recipes:edit", kwargs={"pk": recipe.pk}))

    def test_recipe_detail_shows_manual_tags(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=tagged")
        recipe = Recipe.objects.create(source=source, title="Getaggtes Rezept")
        recipe.tags.add(Tag.objects.create(name="Pasta"), Tag.objects.create(name="Quick"))

        response = self.client.get(recipe.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pasta")
        self.assertContains(response, "Quick")

    def test_index_shows_recipe_tags(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=index-tags")
        recipe = Recipe.objects.create(source=source, title="Tag Kartenrezept")
        recipe.tags.add(Tag.objects.create(name="Pasta"))

        response = self.client.get(reverse("recipes:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tag Kartenrezept")
        self.assertContains(response, "Pasta")

    def test_index_filters_by_tag(self):
        pasta = Tag.objects.create(name="Pasta")
        dessert = Tag.objects.create(name="Dessert")
        pasta_source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=pasta")
        dessert_source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=dessert")
        pasta_recipe = Recipe.objects.create(source=pasta_source, title="Tomatenpasta")
        dessert_recipe = Recipe.objects.create(source=dessert_source, title="Cheesecake")
        pasta_recipe.tags.add(pasta)
        dessert_recipe.tags.add(dessert)

        response = self.client.get(reverse("recipes:index"), {"tag": pasta.slug})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tomatenpasta")
        self.assertNotContains(response, "Cheesecake")

    def test_recipe_detail_shows_possible_duplicates(self):
        first_source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=duplicate-a",
            status=RecipeSource.Status.DONE,
        )
        Recipe.objects.create(
            source=first_source,
            title="Cremige Tomatenpasta",
            ingredients=[
                {"name": "Pasta"},
                {"name": "Tomaten"},
                {"name": "Sahne"},
                {"name": "Parmesan"},
            ],
        )
        second_source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=duplicate-b",
            status=RecipeSource.Status.DONE,
        )
        recipe = Recipe.objects.create(
            source=second_source,
            title="Cremige Tomaten Pasta",
            ingredients=[
                {"name": "Pasta"},
                {"name": "Tomaten"},
                {"name": "Sahne"},
                {"name": "Parmesan"},
            ],
        )

        response = self.client.get(recipe.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mögliche Duplikate")
        self.assertContains(response, "Cremige Tomatenpasta")

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
        self.assertEqual(
            list(RecipeIngredient.objects.filter(recipe=recipe).values_list("name", flat=True)),
            ["200 g Pasta", "Olivenöl"],
        )
        self.assertEqual(recipe.steps, ["Pasta kochen.", "Alles mischen."])
        self.assertEqual(recipe.notes, ["Mit Parmesan servieren."])

    def test_recipe_edit_updates_tags(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=edit-tags")
        recipe = Recipe.objects.create(source=source, title="Tag Rezept")
        quick = Tag.objects.create(name="Quick")
        dessert = Tag.objects.create(name="Dessert")

        response = self.client.post(
            reverse("recipes:edit", kwargs={"pk": recipe.pk}),
            data={
                "title": "Tag Rezept",
                "summary": "",
                "servings": "",
                "prep_time": "",
                "cook_time": "",
                "total_time": "",
                "tags": [str(quick.pk), str(dessert.pk)],
                "ingredients_text": "",
                "steps_text": "",
                "notes_text": "",
            },
        )

        self.assertRedirects(response, recipe.get_absolute_url())
        self.assertEqual(set(recipe.tags.values_list("name", flat=True)), {"Quick", "Dessert"})

    def test_recipe_edit_lists_available_tags(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=edit-tag-list")
        recipe = Recipe.objects.create(source=source, title="Tag Auswahl")
        Tag.objects.create(name="Pasta")

        response = self.client.get(reverse("recipes:edit", kwargs={"pk": recipe.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pasta")

    def test_search_uses_fts_index_for_ingredients_steps_channel_and_transcript(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=fts",
            channel="Test Kitchen",
            transcript="Am Ende kommt frischer Basilikum dazu.",
            status=RecipeSource.Status.DONE,
        )
        recipe = Recipe.objects.create(
            source=source,
            title="Sommerpasta",
            ingredients=[{"name": "Tomaten"}],
            steps=["Pasta kochen und Sauce mischen."],
        )

        searches = ["Tomaten", "Sauce", "Kitchen", "Basilikum"]
        for query in searches:
            with self.subTest(query=query):
                response = self.client.get(reverse("recipes:index"), {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, recipe.title)

    def test_search_index_updates_after_recipe_edit(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=fts-edit")
        recipe = Recipe.objects.create(source=source, title="Alter Titel", ingredients=[])

        response = self.client.post(
            reverse("recipes:edit", kwargs={"pk": recipe.pk}),
            data={
                "title": "Neuer Titel",
                "summary": "",
                "servings": "",
                "prep_time": "",
                "cook_time": "",
                "total_time": "",
                "ingredients_text": "Sardellen",
                "steps_text": "",
                "notes_text": "",
            },
        )

        self.assertRedirects(response, recipe.get_absolute_url())
        response = self.client.get(reverse("recipes:index"), {"q": "Sardellen"})
        self.assertContains(response, "Neuer Titel")

    def test_index_combines_search_and_tag_filter(self):
        pasta = Tag.objects.create(name="Pasta")
        dessert = Tag.objects.create(name="Dessert")
        pasta_source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=search-tag-pasta",
            status=RecipeSource.Status.DONE,
        )
        dessert_source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=search-tag-dessert",
            status=RecipeSource.Status.DONE,
        )
        pasta_recipe = Recipe.objects.create(
            source=pasta_source,
            title="Sommerpasta",
            ingredients=[{"name": "Tomaten"}],
        )
        dessert_recipe = Recipe.objects.create(
            source=dessert_source,
            title="Tomaten Dessert",
            ingredients=[{"name": "Tomaten"}],
        )
        pasta_recipe.tags.add(pasta)
        dessert_recipe.tags.add(dessert)

        response = self.client.get(reverse("recipes:index"), {"q": "Tomaten", "tag": pasta.slug})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sommerpasta")
        self.assertNotContains(response, "Tomaten Dessert")

    def test_tag_generates_slug_from_name(self):
        tag = Tag.objects.create(name="Meal Prep")

        self.assertEqual(tag.slug, "meal-prep")


class ExtractionTests(TestCase):
    def test_enqueue_source_processing_queues_huey_task(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=queue",
            status=RecipeSource.Status.FAILED,
            error_message="Vorheriger Fehler.",
        )

        from unittest.mock import patch

        with patch("recipes.tasks.process_source_task") as task:
            task.return_value.id = "task-123"
            from recipes.services.extractor import enqueue_source_processing

            enqueue_source_processing(source)

        source.refresh_from_db()
        self.assertEqual(source.status, RecipeSource.Status.PROCESSING)
        self.assertEqual(source.error_message, "")
        self.assertEqual(source.queue_task_id, "task-123")
        task.assert_called_once_with(source.pk)

    def test_process_source_creates_recipe(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=test")
        Tag.objects.create(name="Pasta")
        Tag.objects.create(name="Dessert")
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
            "tags": ["pasta", "unknown"],
            "confidence": 0.8,
        }

        with (
            self.settings(LM_STUDIO_MODEL="test"),
            self.subTest("patched services"),
        ):
            from unittest.mock import patch

            with (
                patch("recipes.services.extractor.fetch_video", return_value=video),
                patch(
                    "recipes.services.extractor.extract_recipe_result",
                    return_value=RecipeExtractionResult(
                        payload=payload,
                        lm_studio_model="test-model",
                        prompt_version="test-prompt",
                        raw_response='{"title": "Tomatenpasta"}',
                    ),
                ),
            ):
                process_source(source)

        source.refresh_from_db()
        self.assertEqual(source.status, RecipeSource.Status.DONE)
        recipe = Recipe.objects.get(source=source)
        self.assertEqual(recipe.title, "Tomatenpasta")
        self.assertEqual(list(recipe.tags.values_list("name", flat=True)), ["Pasta"])
        attempt = ExtractionAttempt.objects.get(source=source)
        self.assertEqual(attempt.status, ExtractionAttempt.Status.DONE)
        self.assertEqual(attempt.lm_studio_model, "test-model")
        self.assertEqual(attempt.prompt_version, "test-prompt")
        self.assertEqual(attempt.raw_lm_studio_response, '{"title": "Tomatenpasta"}')
        self.assertIsNotNone(attempt.finished_at)

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
                "recipes.services.extractor.extract_recipe_result",
                return_value=RecipeExtractionResult(
                    payload={"is_recipe": False, "reason": "Kein Rezept.", "confidence": 0.2},
                    lm_studio_model="test-model",
                    prompt_version="test-prompt",
                    raw_response='{"is_recipe": false}',
                ),
            ),
        ):
            process_source(source)

        source.refresh_from_db()
        self.assertEqual(source.status, RecipeSource.Status.FAILED)
        self.assertFalse(Recipe.objects.filter(source=source).exists())
        attempt = ExtractionAttempt.objects.get(source=source)
        self.assertEqual(attempt.status, ExtractionAttempt.Status.FAILED)
        self.assertEqual(attempt.error_details, "Kein Rezept.")
        self.assertEqual(attempt.lm_studio_model, "test-model")

    def test_process_source_marks_repeated_video_as_failed_without_extraction(self):
        existing_source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=existing",
            video_id="same-video",
            status=RecipeSource.Status.DONE,
        )
        Recipe.objects.create(source=existing_source, title="Schon vorhanden")
        source = RecipeSource.objects.create(url="https://youtu.be/same-video")
        video = YouTubeVideo(
            url=source.url,
            video_id="same-video",
            title="Dasselbe Video",
            channel="Test Kitchen",
            thumbnail_url="",
            transcript="Wir kochen Pasta.",
        )

        from unittest.mock import patch

        with (
            patch("recipes.services.extractor.fetch_video", return_value=video),
            patch("recipes.services.extractor.extract_recipe_result") as extract,
        ):
            process_source(source)

        source.refresh_from_db()
        self.assertEqual(source.status, RecipeSource.Status.FAILED)
        self.assertIn("bereits als Rezept", source.error_message)
        extract.assert_not_called()
        attempt = ExtractionAttempt.objects.get(source=source)
        self.assertEqual(attempt.status, ExtractionAttempt.Status.FAILED)
        self.assertIn("bereits als Rezept", attempt.error_details)

    def test_process_source_records_lmstudio_error_details(self):
        source = RecipeSource.objects.create(url="https://www.youtube.com/watch?v=lm-error")
        video = YouTubeVideo(
            url=source.url,
            video_id="lm-error",
            title="Pasta Video",
            channel="Test Kitchen",
            thumbnail_url="",
            transcript="Wir kochen Pasta.",
        )
        error = lmstudio.RecipeExtractionError(
            "Keine valide JSON-Antwort.",
            lm_studio_model="broken-model",
            prompt_version="test-prompt",
            raw_response="kein json",
        )

        from unittest.mock import patch

        with (
            patch("recipes.services.extractor.fetch_video", return_value=video),
            patch("recipes.services.extractor.extract_recipe_result", side_effect=error),
        ):
            process_source(source)

        source.refresh_from_db()
        self.assertEqual(source.status, RecipeSource.Status.FAILED)
        attempt = ExtractionAttempt.objects.get(source=source)
        self.assertEqual(attempt.status, ExtractionAttempt.Status.FAILED)
        self.assertEqual(attempt.error_details, "Keine valide JSON-Antwort.")
        self.assertEqual(attempt.lm_studio_model, "broken-model")
        self.assertEqual(attempt.prompt_version, "test-prompt")
        self.assertEqual(attempt.raw_lm_studio_response, "kein json")

    def test_source_detail_shows_extraction_history(self):
        source = RecipeSource.objects.create(
            url="https://www.youtube.com/watch?v=history",
            status=RecipeSource.Status.FAILED,
        )
        ExtractionAttempt.objects.create(
            source=source,
            status=ExtractionAttempt.Status.FAILED,
            lm_studio_model="history-model",
            prompt_version="test-prompt",
            raw_lm_studio_response="kein json",
            error_details="Keine valide JSON-Antwort.",
        )

        response = self.client.get(reverse("recipes:source_detail", kwargs={"pk": source.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Extraktionshistorie")
        self.assertContains(response, "history-model")
        self.assertContains(response, "Keine valide JSON-Antwort.")


class YouTubeTests(TestCase):
    def test_fetch_video_maps_rate_limit_to_friendly_error(self):
        from unittest.mock import patch

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def extract_info(self, url, download=False):
                raise RuntimeError("HTTP Error 429: Too Many Requests")

        with patch("recipes.services.youtube.YoutubeDL", FakeYoutubeDL):
            with self.assertRaises(YouTubeRateLimited) as error:
                fetch_video("https://www.youtube.com/watch?v=rate-limit")

        self.assertIn("HTTP 429", str(error.exception))
        self.assertIn("YT_DLP_COOKIES_FILE", str(error.exception))

    def test_extract_transcript_reports_timedtext_rate_limit(self):
        from unittest.mock import patch

        from recipes.services.youtube import _extract_transcript

        info = {
            "automatic_captions": {
                "de": [
                    {
                        "ext": "json3",
                        "url": "https://www.youtube.com/api/timedtext?v=test",
                    }
                ]
            }
        }

        with patch(
            "recipes.services.youtube._download_track",
            side_effect=YouTubeRateLimited("HTTP Error 429: Too Many Requests"),
        ):
            with self.assertRaises(YouTubeRateLimited) as error:
                _extract_transcript(info)

        self.assertIn("/api/timedtext", str(error.exception))
        self.assertIn("Metadaten konnten gelesen werden", str(error.exception))

    def test_preferred_languages_uses_app_setting_first(self):
        from recipes.services.youtube import _preferred_languages

        AppSettings.objects.create(pk=1, language_preference="fr, es")
        collection = {"de": [], "fr": [], "en": [], "es": []}

        self.assertEqual(_preferred_languages(collection), ["fr", "es", "de", "en"])


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

    def test_resolve_model_prefers_instruct_model(self):
        from unittest.mock import patch

        response = _FakeResponse(
            {
                "data": [
                    {"id": "google/gemma-4-e2b"},
                    {"id": "text-embedding-nomic-embed-text-v1.5"},
                    {"id": "mistralai/mistral-7b-instruct-v0.3"},
                ]
            }
        )

        with (
            self.settings(LM_STUDIO_MODEL=""),
            patch("recipes.services.lmstudio.httpx.get", return_value=response),
        ):
            self.assertEqual(
                lmstudio._resolve_model("http://localhost:1234/v1"),
                "mistralai/mistral-7b-instruct-v0.3",
            )

    def test_parse_json_content_accepts_markdown_wrapped_json(self):
        content = """
        Hier ist das JSON:
        ```json
        {"is_recipe": false, "reason": "Kein Rezept.", "confidence": 0.3}
        ```
        """

        payload = lmstudio._parse_json_content(content)

        self.assertFalse(payload["is_recipe"])

    def test_parse_json_content_accepts_prefixed_json(self):
        content = 'Antwort: {"is_recipe": false, "reason": "Kein Rezept.", "confidence": 0.3}'

        payload = lmstudio._parse_json_content(content)

        self.assertFalse(payload["is_recipe"])

    def test_normalize_recipe_payload_includes_tag_strings(self):
        payload = lmstudio._normalize_recipe_payload(
            {
                "is_recipe": True,
                "title": "Pasta",
                "tags": ["Pasta", "  Quick  ", ""],
            }
        )

        self.assertEqual(payload["tags"], ["Pasta", "Quick"])

    def test_build_prompt_includes_allowed_tags(self):
        Tag.objects.create(name="Dessert")
        Tag.objects.create(name="Quick")

        prompt = lmstudio._build_prompt("Titel", "Kanal", "Transkript")

        self.assertIn("Dessert", prompt)
        self.assertIn("Quick", prompt)

    def test_extract_recipe_error_includes_response_excerpt(self):
        from unittest.mock import patch

        response = _FakeResponse({"choices": [{"message": {"content": "Ich kann das nicht."}}]})

        with (
            self.settings(LM_STUDIO_MODEL="loaded-model"),
            patch("recipes.services.lmstudio.httpx.post", return_value=response),
        ):
            with self.assertRaises(lmstudio.RecipeExtractionError) as error:
                lmstudio.extract_recipe("Titel", "Kanal", "Transkript")

        self.assertIn("Antwortauszug", str(error.exception))
        self.assertIn("Ich kann das nicht", str(error.exception))

    def test_extract_recipe_uses_saved_app_settings(self):
        from unittest.mock import patch

        AppSettings.objects.create(
            pk=1,
            lm_studio_base_url="http://lmstudio.test/v1",
            lm_studio_model="saved-model",
            transcript_limit=1000,
            extraction_prompt="Custom system prompt.",
        )
        response = _FakeResponse(
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

        with patch("recipes.services.lmstudio.httpx.post", return_value=response) as post:
            transcript = f"{'a' * 1000}TRUNCATED"
            payload = lmstudio.extract_recipe("Titel", "Kanal", transcript)

        self.assertFalse(payload["is_recipe"])
        self.assertEqual(post.call_args.args[0], "http://lmstudio.test/v1/chat/completions")
        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["model"], "saved-model")
        self.assertEqual(request_payload["messages"][0]["content"], "Custom system prompt.")
        self.assertIn("a" * 1000, request_payload["messages"][1]["content"])
        self.assertNotIn("TRUNCATED", request_payload["messages"][1]["content"])

    def test_connection_status_lists_loaded_models(self):
        from unittest.mock import patch

        response = _FakeResponse(
            {
                "data": [
                    {"id": "loaded-model"},
                    {"id": "text-embedding-model"},
                ]
            }
        )

        with patch("recipes.services.lmstudio.httpx.get", return_value=response):
            status = lmstudio.connection_status("http://localhost:1234/v1")

        self.assertTrue(status.is_available)
        self.assertEqual(status.model_ids, ["loaded-model", "text-embedding-model"])

    def test_admin_app_settings_shows_lmstudio_status(self):
        from unittest.mock import patch

        app_settings = AppSettings.objects.create(
            pk=1,
            lm_studio_base_url="http://localhost:1234/v1",
        )
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        status = lmstudio.LmStudioConnectionStatus(
            base_url="http://localhost:1234/v1",
            is_available=True,
            model_ids=["loaded-model"],
        )
        self.client.force_login(user)

        with patch("recipes.admin.lm_studio_connection_status", return_value=status):
            response = self.client.get(
                reverse("admin:recipes_appsettings_change", kwargs={"object_id": app_settings.pk})
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reachable")
        self.assertContains(response, "loaded-model")


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
