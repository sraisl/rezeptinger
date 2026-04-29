from django.urls import path

from . import views

app_name = "recipes"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/extractions/", views.api_create_extraction, name="api_create_extraction"),
    path("api/extractions/<int:pk>/", views.api_extraction_status, name="api_extraction_status"),
    path("data/", views.data_tools, name="data_tools"),
    path("data/export/", views.data_export, name="data_export"),
    path("data/import/", views.data_import, name="data_import"),
    path("sources/", views.create_source, name="create_source"),
    path("sources/<int:pk>/", views.source_detail, name="source_detail"),
    path("sources/<int:pk>/status/", views.source_status, name="source_status"),
    path("sources/<int:pk>/retry/", views.retry_source, name="retry_source"),
    path("recipes/<int:pk>/", views.detail, name="detail"),
]
