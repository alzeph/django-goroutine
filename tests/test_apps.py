from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from django.apps import apps

from django_goroutine import executors


def test_ready_warms_the_db_pool():
    apps.get_app_config("django_goroutine").ready()
    assert isinstance(executors.get_db_executor(), ThreadPoolExecutor)


def test_ready_leaves_the_cpu_pool_lazy():
    # Contrairement au pool @db, le pool @cpu ne doit pas être créé par
    # ready() : ready() tourne pour n'importe quel process qui charge l'app
    # Django (migrate, shell, mypy via django-stubs...), pas seulement un
    # serveur applicatif — spawner des process OS à chaque fois en ferait
    # une source de fuites de ressources sur des commandes qui n'utilisent
    # jamais @cpu.
    apps.get_app_config("django_goroutine").ready()
    assert executors._cpu_executor is None
