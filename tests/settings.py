from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "test-secret-key"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_goroutine",
]

MIDDLEWARE: list[str] = []

# Un fichier, pas ":memory:" : les tests sur @db exercent volontairement
# plusieurs threads (pool dédié), et une base sqlite en mémoire n'est pas
# partagée entre connexions/threads distincts. Combiné à
# `@pytest.mark.django_db(transaction=True)` (pas de transaction enveloppante
# non commitée), c'est ce qui permet à un thread du pool de lire ce qu'un
# autre thread vient d'écrire — exactement le scénario que le pool @db est
# censé rendre sûr.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
        # sqlite n'a qu'un verrou d'écriture global : sans un timeout
        # généreux, un thread du pool @db qui écrit pendant qu'un autre
        # écrit déjà lève "database is locked" au lieu d'attendre son tour.
        "OPTIONS": {"timeout": 20},
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "tests.urls"

GOROUTINE = {
    "DB_POOL_SIZE": 4,
    "CPU_POOL_SIZE": 2,
}
