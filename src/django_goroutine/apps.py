import atexit
import logging

from django.apps import AppConfig

logger = logging.getLogger("django_goroutine")


class DjangoGoroutineConfig(AppConfig):
    name = "django_goroutine"
    verbose_name = "Django Goroutine"

    def ready(self) -> None:
        from django_goroutine.executors import get_db_executor, reset_executors

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

        # Django n'a pas de signal générique d'arrêt propre pour une app
        # réutilisable (contrairement à `ready()` au démarrage) — le
        # lifespan ASGI existe, mais brancher dessus demande un câblage
        # explicite côté projet, pas quelque chose qu'une app installable
        # peut accrocher automatiquement. `atexit` couvre le cas par
        # défaut sans configuration : ferme proprement threads et process
        # à la fin du process plutôt que de compter sur leur nettoyage
        # implicite (`ThreadPoolExecutor`/`ProcessPoolExecutor` s'en
        # chargent déjà via leur propre `atexit`, mais dans un ordre non
        # garanti par rapport aux autres handlers — celui-ci est explicite
        # et journalise le résultat).
        atexit.register(reset_executors)
        logger.debug("django_goroutine: app prête, arrêt propre enregistré (atexit)")
