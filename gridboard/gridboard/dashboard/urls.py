from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("raw/", views.dashboard, {"mode": "raw"}, name="raw"),
    path("aggregate/", views.dashboard, {"mode": "aggregate"}, name="aggregate"),
    path("api/<str:mode>/<str:panel>/", views.panel_data, name="panel_data"),
]
