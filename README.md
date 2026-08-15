# django-goroutine

[![CI](https://github.com/alzeph/django-goroutine/actions/workflows/ci.yml/badge.svg)](https://github.com/alzeph/django-goroutine/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/django-goroutine.svg)](https://pypi.org/project/django-goroutine/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](pyproject.toml)

> **Release candidate.** `django-goroutine` est en `1.0.0rc1` : l'API est
> considérée figée mais n'a pas encore été éprouvée par un usage réel en
> dehors de ce dépôt. Les retours (issues, cas d'usage, bugs) sont les
> bienvenus avant de tagger la version `1.0.0` finale — voir
> [RELEASING.md](RELEASING.md).

Un orchestrateur structuré de tâches concurrentes pour Django, inspiré du
modèle de concurrence de Go — sans prétendre le reproduire à l'identique.

## Le problème

Django sait exécuter des vues et des méthodes ORM en `async`/`await`, mais
ne donne aucun outil clé en main pour lancer plusieurs opérations
indépendantes en parallèle dans une vue. À la main avec `asyncio.gather`, on
se heurte vite à trois obstacles : le pool de connexions de l'ORM (historique
sync) qui se comporte mal sous plusieurs threads, le contexte de requête
(utilisateur, langue, session) qui ne se propage pas toujours proprement, et
une dizaine de lignes de tuyauterie pour annuler/nettoyer si une sous-tâche
échoue. `django-goroutine` fournit `group()` (au-dessus d'`asyncio.TaskGroup`)
et `cpu_map()` (au-dessus d'un `ProcessPoolExecutor` persistant) pour couvrir
ces trois obstacles, avec des erreurs par tâche renvoyées en
[`pycatch.Result`](https://pypi.org/project/pycatch-safe/) plutôt que levées.

## Ce que "goroutine" ne veut pas dire ici

Une goroutine Go est un thread vert géré par le runtime, capable de migrer
entre threads OS. Python garde une boucle d'événements unique et
coopérative : `group()` ne réplique pas ce modèle, il en reprend l'esprit —
le point d'appel décide quoi lancer en concurrence, pas la fonction
elle-même — avec trois façons distinctes d'exécuter une tâche selon sa
nature réelle :

| Décorateur | Nature de la tâche | Exécutée sur |
|---|---|---|
| `@io` (ou une coroutine non décorée) | Attente réseau/disque (`async def`) | La boucle d'événements, sans thread ni process dédié |
| `@db` | Appel ORM sync bloquant | Le pool de threads dédié (`GOROUTINE["DB_POOL_SIZE"]`) |
| `@cpu` | Calcul CPU-bound sync | Le pool de process dédié (`GOROUTINE["CPU_POOL_SIZE"]`) |

Ce choix explicite plutôt qu'une détection automatique est délibéré : une
heuristique (timing, introspection) pour deviner la nature d'une fonction
serait peu fiable et reproduirait justement les bugs sournois que ce projet
cherche à éviter.

## Installation

```bash
uv add django-goroutine
pip install django-goroutine
```

Une release candidate n'étant pas une version finale, PyPI ne l'installe
pas par défaut avec `pip install django-goroutine` — utilisez `--pre` ou
fixez la version exacte tant que `1.0.0` n'est pas taggé :

```bash
uv add "django-goroutine==1.0.0rc1"
pip install "django-goroutine==1.0.0rc1"
```

```python
# settings.py
INSTALLED_APPS = [
    ...,
    "django_goroutine",
]
```

`ready()` démarre le pool de threads (`@db`) au boot plutôt qu'au premier
appel, pour ne pas payer son coût de création sur la première requête qui
l'utilise. Le pool de process (`@cpu`) reste volontairement paresseux
(créé au premier appel réel) — voir la section Limitations connues.

## Démarrage rapide

```python
from django_goroutine import db, group, io


@db
def fetch_user(user_id: int) -> User:
    return User.objects.get(pk=user_id)


@io
async def fetch_avatar(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.content


async def profile_view(request, user_id):
    async with group() as g:
        user_task = g.go(fetch_user, user_id)
        avatar_task = g.go(fetch_avatar, avatar_url)

    match user_task.result():
        case Ok(user):
            ...
        case Err(err):
            ...
```

`fetch_user` et `fetch_avatar` tournent en parallèle : le temps de réponse
de la vue tombe au temps de la plus lente des deux, pas à leur somme.

### Héritage des appels internes

Une fonction appelée *depuis* `fetch_user` (une aide interne, un second
appel ORM) s'exécute simplement dans le même appel de pile, sur le même
thread — aucune décoration supplémentaire n'est nécessaire ni utile. Le
décorateur ne sert qu'au moment où `Group.go()` dispatche la tâche, pas à la
propagation interne des appels.

### Erreurs par tâche, pas d'annulation en cascade sur erreur métier

N'importe quelle exception levée par une tâche dispatchée devient un `Err`
porté par son `TaskHandle` : elle ne fait jamais planter les tâches sœurs ni
le bloc englobant — `group()` est un `sync.WaitGroup`, pas un `errgroup` à
annulation automatique sur erreur métier. L'annulation reste possible, mais
seulement de façon structurelle : si le bloc `async with group()` lui-même
est annulé de l'extérieur (timeout du serveur ASGI, déconnexion client), les
tâches encore en cours sont annulées par `asyncio.TaskGroup`, comme
n'importe quel autre `await`.

```python
async with group() as g:
    a = g.go(fetch_user, user_id)      # échoue
    b = g.go(fetch_avatar, avatar_url) # continue quand même, n'est pas annulée

a.result()  # Err(UserDoesNotExist(...))
b.result()  # Ok(b"...")
```

`TaskHandle.result()` ne peut être lu qu'une fois le bloc `async with
group()` refermé — l'appeler avant lève `RuntimeError`.

## Paralléliser un calcul CPU-bound (`cpu_map`)

`@cpu` sur `group().go()` ne fait gagner du temps que sur du travail déjà
découpé en unités indépendantes. Une seule fonction CPU-bound dispatchée
seule n'accélère pas — exactement comme une goroutine Go seule n'accélère
pas un calcul monolithique : le gain vient toujours du découpage en unités
indépendantes réparties sur plusieurs cœurs, jamais de l'outil
d'orchestration en lui-même. `cpu_map()` couvre le cas où ce découpage
existe déjà :

```python
from django_goroutine import cpu_map


def resize_one(image_bytes: bytes) -> bytes:
    ...


async def batch_resize_view(request, images):
    results = await cpu_map(resize_one, images)
    ...
```

`fn` doit être une fonction sync CPU-bound, importable au niveau module
(contrainte de `pickle` du `ProcessPoolExecutor` sous-jacent) — jamais une
lambda, une closure, ou une méthode d'instance liée. Un échec sur un élément
ne fait pas échouer les autres : chaque résultat est un `Result`
indépendant, dans l'ordre d'entrée.

Le GIL empêche deux threads d'exécuter du bytecode Python en parallèle : si
votre calcul lourd passe déjà par une bibliothèque C qui relâche le GIL
(numpy, Pillow, OpenCV, hashlib...), `@db`-style thread offload suffirait —
`@cpu`/`cpu_map()` n'apportent un vrai gain que pour du code Python pur
CPU-bound, via des process séparés.

## Configuration

```python
GOROUTINE = {
    "DB_POOL_SIZE": 10,                # taille du pool de threads @db
    "CPU_POOL_SIZE": os.cpu_count(),   # taille du pool de process @cpu
}
```

## Limitations connues

- **sqlite et écritures concurrentes.** sqlite n'a qu'un verrou d'écriture
  global : plusieurs fonctions `@db` qui écrivent en parallèle contre une
  base sqlite peuvent lever `OperationalError("database is locked")`.
  PostgreSQL et MySQL encaissent des écritures concurrentes sans ce verrou —
  en développement avec sqlite, augmentez `OPTIONS.timeout` ou évitez les
  écritures concurrentes sur le même pool.
- **Le pool `@cpu` est paresseux, pas démarré par `apps.ready()`.** Deux
  raisons, pas une question de goût : `ready()` s'exécute pour n'importe
  quel process qui charge l'app Django — `migrate`, `shell`, ou même
  `mypy` via le plugin django-stubs, qui appelle `django.setup()` pour de
  vrai — pas seulement un serveur applicatif ; spawn des process OS à
  chaque fois en aurait fait une source de fuites de ressources sur des
  commandes qui n'utilisent jamais `@cpu`. Et démarrer un
  `ProcessPoolExecutor` avant un fork (gunicorn `--preload`) est une
  source connue de blocages en `multiprocessing` — la création paresseuse
  élimine ce risque au passage, le pool étant créé dans chaque worker
  après le fork, pas avant. Le pool utilise en outre le contexte `spawn`
  plutôt que le `fork` par défaut de Linux : forker un process
  multi-threadé (boucle asyncio + pool `@db`) peut figer l'enfant si un
  thread tenait un verrou interne au moment du fork — `spawn` démarre un
  interpréteur neuf, plus lent au premier appel mais sans cet héritage.
  Chaque worker `spawn` appelle `django.setup()` à son démarrage (via
  l'`initializer` du pool) pour rester importable même si son module
  touche, même indirectement, à des modèles Django.
- **Pas d'annulation automatique des tâches sœurs sur erreur métier.**
  `group()` est volontairement un `sync.WaitGroup`, pas un `errgroup` à
  annulation sur premier échec — voir la section dédiée ci-dessus. Un mode
  `cancel_on_error` pourrait être ajouté dans une version mineure future si
  le besoin se confirme à l'usage.
- **`@cpu`/`cpu_map()` exigent des fonctions picklables au niveau module.**
  Contrainte de `ProcessPoolExecutor`, pas de ce projet — une lambda, une
  closure ou une méthode liée échouent silencieusement à être picklées.

## Développement

```bash
uv sync --group dev

uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest --cov=django_goroutine --cov-report=term-missing
```

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour contribuer,
[CHANGELOG.md](CHANGELOG.md) pour l'historique des versions, et
[RELEASING.md](RELEASING.md) pour le processus de publication.

## Licence

[MIT](LICENSE)
