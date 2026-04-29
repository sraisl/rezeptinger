from huey.contrib.djhuey import db_task

from recipes.models import RecipeSource
from recipes.services.extractor import process_source


@db_task()
def process_source_task(source_id: int) -> None:
    try:
        source = RecipeSource.objects.get(pk=source_id)
    except RecipeSource.DoesNotExist:
        return
    process_source(source)
