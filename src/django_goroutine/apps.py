from django.apps import AppConfig


class DjangoGoroutineConfig(AppConfig):
    name = "django_goroutine"
    verbose_name = "Django Goroutine"

    def ready(self) -> None:
        from django_goroutine.executors import get_cpu_executor, get_db_executor

        # Démarré au boot plutôt qu'au premier appel : évite de payer le
        # coût de création du pool (et, pour @cpu, le spawn des process)
        # sur la première requête qui l'utilise.
        get_db_executor()
        get_cpu_executor()
