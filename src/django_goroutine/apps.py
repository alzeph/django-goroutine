from django.apps import AppConfig


class DjangoGoroutineConfig(AppConfig):
    name = "django_goroutine"
    verbose_name = "Django Goroutine"

    def ready(self) -> None:
        from django_goroutine.executors import get_db_executor

        # Seul le pool de threads (@db) est démarré au boot : c'est peu
        # coûteux et évite de payer sa création sur la première requête.
        # Le pool de process (@cpu) reste paresseux, créé au premier appel
        # réel — `ready()` s'exécute pour n'importe quel process qui charge
        # l'app Django (migrate, shell, mypy via le plugin django-stubs qui
        # appelle django.setup() pour de vrai...), pas seulement un serveur
        # applicatif. Spawn des process OS à chaque `ready()` en faisait
        # une source de fuites de sémaphores sur des commandes qui
        # n'utilisent jamais @cpu — et évite au passage tout risque de
        # ProcessPoolExecutor créé avant un fork (gunicorn --preload).
        get_db_executor()
