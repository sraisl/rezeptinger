from django.db import migrations, models
import django.db.models.deletion


def ingredient_payloads(value):
    payloads = []
    for ingredient in value or []:
        if isinstance(ingredient, dict):
            name = str(ingredient.get("name") or "").strip()
            if not name:
                joined = " ".join(
                    str(ingredient.get(key, "")).strip()
                    for key in ("quantity", "unit", "note")
                    if ingredient.get(key)
                )
                name = joined or "Zutat"
            payloads.append(
                {
                    "quantity": str(ingredient.get("quantity") or "").strip(),
                    "unit": str(ingredient.get("unit") or "").strip(),
                    "name": name,
                    "note": str(ingredient.get("note") or "").strip(),
                }
            )
        else:
            name = str(ingredient).strip()
            if name:
                payloads.append({"quantity": "", "unit": "", "name": name, "note": ""})
    return payloads


def migrate_ingredients(apps, schema_editor):
    Recipe = apps.get_model("recipes", "Recipe")
    RecipeIngredient = apps.get_model("recipes", "RecipeIngredient")

    for recipe in Recipe.objects.iterator():
        for position, ingredient in enumerate(ingredient_payloads(recipe.ingredients)):
            RecipeIngredient.objects.create(
                recipe=recipe,
                position=position,
                quantity=ingredient["quantity"],
                unit=ingredient["unit"],
                name=ingredient["name"],
                note=ingredient["note"],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0002_recipe_search_fts"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecipeIngredient",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("position", models.PositiveIntegerField(default=0)),
                ("quantity", models.CharField(blank=True, max_length=80)),
                ("unit", models.CharField(blank=True, max_length=80)),
                ("name", models.CharField(max_length=255)),
                ("note", models.CharField(blank=True, max_length=255)),
                (
                    "recipe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ingredient_items",
                        to="recipes.recipe",
                    ),
                ),
            ],
            options={
                "ordering": ["position", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="recipeingredient",
            index=models.Index(fields=["name"], name="recipes_rec_name_80a9f0_idx"),
        ),
        migrations.RunPython(migrate_ingredients, migrations.RunPython.noop),
    ]

