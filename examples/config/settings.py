"""Réglages minimaux pour explorer django-goroutine sans rien configurer
d'autre — voir examples/README.md pour les commandes à lancer."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "insecure-demo-key-do-not-use-in-production"  # noqa: S105 - projet de démo uniquement
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_goroutine",
    "playground",
]

MIDDLEWARE: list[str] = []

ROOT_URLCONF = "config.urls"

# TEST.NAME est nécessaire même en dehors des tests automatisés du paquet
# lui-même : Django bascule sqlite sur ":memory:" par défaut pour la base
# de *test* quel que soit NAME, ce qui casserait `manage.py test` sur ce
# projet de démo si on l'utilise un jour pour explorer @db plus loin.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "TEST": {"NAME": BASE_DIR / "db.sqlite3"},
        "OPTIONS": {"timeout": 20},
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DB_MAX_PENDING/CPU_MAX_PENDING volontairement bas (au lieu du défaut
# POOL_SIZE * 4) pour que /backpressure/ rende la sérialisation visible
# sans avoir à lancer des dizaines de requêtes concurrentes à la main.
GOROUTINE = {
    "DB_POOL_SIZE": 5,
    "CPU_POOL_SIZE": 2,
    "DB_MAX_PENDING": 2,
    "CPU_MAX_PENDING": 2,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django_goroutine": {"handlers": ["console"], "level": "DEBUG"},
    },
}
