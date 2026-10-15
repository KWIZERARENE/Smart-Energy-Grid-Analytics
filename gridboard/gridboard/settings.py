"""Django settings for the Smart Energy Grid dashboards (Assignment I, Section 7).

# Secrets come from environment variables; set them before running:
# set PGPASSWORD=<your password>
# No Django cache is configured, so no query result is ever cached (7.4 requirement).

"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-secret")
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "dashboard",
]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "gridboard.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": []},
}]
WSGI_APPLICATION = "gridboard.wsgi.application"

# Raw SQL is used everywhere (time_bucket and continuous aggregates), so the
# database settings are read by dashboard/db.py, not by the Django ORM.
DATABASES = {}

# Explicitly disable caching: dummy backend stores nothing.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}

TIME_ZONE = "Africa/Kigali"
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PG = {
    "dbname": os.environ.get("PGDATABASE", "smartgrid"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", "CHANGE_ME"),
    "host": os.environ.get("PGHOST", "127.0.0.1"),
    "port": int(os.environ.get("PGPORT", "5433")),
}
