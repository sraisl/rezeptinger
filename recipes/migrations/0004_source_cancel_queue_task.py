from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0003_recipeingredient"),
    ]

    operations = [
        migrations.AddField(
            model_name="recipesource",
            name="queue_task_id",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterField(
            model_name="recipesource",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Wartet"),
                    ("processing", "Wird verarbeitet"),
                    ("done", "Fertig"),
                    ("failed", "Fehlgeschlagen"),
                    ("cancelled", "Abgebrochen"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]

