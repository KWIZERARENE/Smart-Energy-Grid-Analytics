6
from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("raw/", views.dashboard, {"mode": "raw"}, name="raw"),
    path("aggregate/", views.dashboard, {"mode": "aggregate"}, name="aggregate"),
    path("forecast/", views.forecast_view, name="forecast"),
    path("api/forecast/data/", views.forecast_data, name="forecast_data"),
    path("api/forecast/export/", views.forecast_export_csv, name="forecast_export_csv"),
    path("api/<str:mode>/<str:panel>/", views.panel_data, name="panel_data"),
]


