import json

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import RecipeEditForm, RecipeSourceForm
from .models import Recipe, RecipeSource
from .services.extractor import enqueue_source_processing
from .services.portable_data import export_catalog, import_catalog
from .services.search import search_recipes


def index(request):
    query = request.GET.get("q", "").strip()
    recipes = search_recipes(query) if query else Recipe.objects.select_related("source")
    sources = RecipeSource.objects.exclude(status=RecipeSource.Status.DONE)[:8]

    return render(
        request,
        "recipes/index.html",
        {
            "form": RecipeSourceForm(),
            "recipes": recipes,
            "sources": sources,
            "query": query,
        },
    )


@require_http_methods(["POST"])
def create_source(request):
    form = RecipeSourceForm(request.POST)
    if not form.is_valid():
        recipes = Recipe.objects.select_related("source")
        return render(
            request,
            "recipes/index.html",
            {"form": form, "recipes": recipes, "sources": []},
        )

    source, created = RecipeSource.objects.get_or_create(url=form.cleaned_data["url"])
    if source.status == RecipeSource.Status.DONE and hasattr(source, "recipe"):
        messages.info(request, "Dieses Rezept ist bereits im Katalog.")
        return redirect(source.recipe)

    if not created:
        messages.info(request, "Die Quelle wird erneut verarbeitet.")

    enqueue_source_processing(source)
    messages.info(request, "Extraktion gestartet.")
    return redirect("recipes:source_detail", pk=source.pk)


@require_http_methods(["POST"])
def retry_source(request, pk):
    source = get_object_or_404(RecipeSource, pk=pk)

    if source.status == RecipeSource.Status.DONE and hasattr(source, "recipe"):
        messages.info(request, "Dieses Rezept ist bereits im Katalog.")
        return redirect(source.recipe)

    enqueue_source_processing(source)
    messages.info(request, "Extraktion erneut gestartet.")
    return redirect("recipes:source_detail", pk=source.pk)


def detail(request, pk):
    recipe = get_object_or_404(Recipe.objects.select_related("source"), pk=pk)
    return render(request, "recipes/detail.html", {"recipe": recipe})


@require_http_methods(["GET", "POST"])
def edit_recipe(request, pk):
    recipe = get_object_or_404(Recipe.objects.select_related("source"), pk=pk)

    if request.method == "POST":
        form = RecipeEditForm(request.POST, instance=recipe)
        if form.is_valid():
            form.save()
            messages.success(request, "Rezept wurde gespeichert.")
            return redirect(recipe)
    else:
        form = RecipeEditForm(instance=recipe)

    return render(request, "recipes/edit.html", {"form": form, "recipe": recipe})


def source_detail(request, pk):
    source = get_object_or_404(RecipeSource, pk=pk)
    return render(request, "recipes/source_detail.html", {"source": source})


def source_status(request, pk):
    source = get_object_or_404(RecipeSource, pk=pk)
    return JsonResponse(_source_status_payload(request, source))


def data_tools(request):
    return render(request, "recipes/data_tools.html")


def data_export(request):
    payload = export_catalog()
    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json",
    )
    response["Content-Disposition"] = f'attachment; filename="rezeptinger-{timestamp}.json"'
    return response


# Intentional for local/headless import via curl and shortcuts; this app has no user accounts.
@csrf_exempt  # nosemgrep: python.django.security.audit.csrf-exempt.csrf-exempt
@require_http_methods(["POST"])
def data_import(request):
    try:
        payload = _import_payload(request)
        result = import_catalog(payload)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if _wants_json(request):
            return JsonResponse({"error": str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect("recipes:data_tools")

    if _wants_json(request):
        return JsonResponse({"imported": result})

    messages.success(
        request,
        f"Import abgeschlossen: {result['sources']} Quellen, {result['recipes']} Rezepte.",
    )
    return redirect("recipes:index")


# Intentional for local/headless extraction via curl and shortcuts; this app has no user accounts.
@csrf_exempt  # nosemgrep: python.django.security.audit.csrf-exempt.csrf-exempt
@require_http_methods(["POST"])
def api_create_extraction(request):
    payload = _request_payload(request)
    form = RecipeSourceForm({"url": payload.get("url", "")})

    if not form.is_valid():
        return JsonResponse({"error": "Bitte eine valide YouTube-URL übergeben."}, status=400)

    source, created = RecipeSource.objects.get_or_create(url=form.cleaned_data["url"])
    should_enqueue = created or source.status != RecipeSource.Status.PROCESSING
    if source.status == RecipeSource.Status.DONE and hasattr(source, "recipe"):
        should_enqueue = False

    if should_enqueue:
        enqueue_source_processing(source)

    status_code = 200 if source.status == RecipeSource.Status.DONE else 202
    return JsonResponse(_source_status_payload(request, source), status=status_code)


def api_extraction_status(request, pk):
    source = get_object_or_404(RecipeSource, pk=pk)
    return JsonResponse(_source_status_payload(request, source))


def _request_payload(request) -> dict:
    if request.content_type == "application/json":
        try:
            return json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST


def _import_payload(request) -> dict:
    uploaded = request.FILES.get("file")
    if uploaded:
        raw = uploaded.read().decode("utf-8")
        return json.loads(raw)

    return json.loads(request.body or "{}")


def _wants_json(request) -> bool:
    return request.content_type == "application/json" or "application/json" in request.headers.get(
        "Accept", ""
    )


def _source_status_payload(request, source: RecipeSource) -> dict:
    recipe_url = ""
    recipe_payload = None
    if source.status == RecipeSource.Status.DONE and hasattr(source, "recipe"):
        recipe_url = source.recipe.get_absolute_url()
        recipe_payload = _recipe_payload(source.recipe)

    status_url = reverse_url(request, "recipes:api_extraction_status", pk=source.pk)
    detail_url = reverse_url(request, "recipes:source_detail", pk=source.pk)
    absolute_recipe_url = request.build_absolute_uri(recipe_url) if recipe_url else ""

    return {
        "id": source.pk,
        "url": source.url,
        "status": source.status,
        "status_display": source.get_status_display(),
        "error_message": source.error_message,
        "status_url": status_url,
        "detail_url": detail_url,
        "recipe_url": absolute_recipe_url,
        "title": source.title or "Quelle",
        "recipe": recipe_payload,
    }


def _recipe_payload(recipe: Recipe) -> dict:
    return {
        "id": recipe.pk,
        "title": recipe.title,
        "summary": recipe.summary,
        "servings": recipe.servings,
        "prep_time": recipe.prep_time,
        "cook_time": recipe.cook_time,
        "total_time": recipe.total_time,
        "ingredients": recipe.ingredient_payloads(),
        "steps": recipe.steps,
        "notes": recipe.notes,
        "confidence": recipe.confidence,
    }


def reverse_url(request, viewname: str, **kwargs) -> str:
    from django.urls import reverse

    return request.build_absolute_uri(reverse(viewname, kwargs=kwargs))
