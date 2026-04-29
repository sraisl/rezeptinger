from django.db import migrations


CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS recipes_recipe_fts USING fts5(
    recipe_id UNINDEXED,
    title,
    ingredients,
    steps,
    channel,
    transcript
);
"""


DROP_FTS = "DROP TABLE IF EXISTS recipes_recipe_fts;"


def rebuild_search_index(apps, schema_editor):
    Recipe = apps.get_model("recipes", "Recipe")
    connection = schema_editor.connection

    def ingredient_text(ingredients):
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

    def list_text(values):
        return " ".join(str(value) for value in values or [])

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM recipes_recipe_fts")
        for recipe in Recipe.objects.select_related("source").iterator():
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
                    ingredient_text(recipe.ingredients),
                    list_text(recipe.steps),
                    recipe.source.channel,
                    recipe.source.transcript,
                ],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(CREATE_FTS, DROP_FTS),
        migrations.RunPython(rebuild_search_index, migrations.RunPython.noop),
    ]

