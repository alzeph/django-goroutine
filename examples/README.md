# django-goroutine — playground

Un projet Django minimal pour explorer `group()`, `cpu_map()`, le timeout
et la backpressure sans rien configurer soi-même : il tourne dans le même
environnement virtuel que le paquet lui-même (`django-goroutine` y est
déjà installé, en editable, dès `uv sync`).

## Lancer

Depuis la racine du dépôt :

```bash
uv sync --group dev                          # si ce n'est pas déjà fait
uv run python examples/manage.py migrate
uv run python examples/manage.py runserver
```

Puis ouvrir <http://127.0.0.1:8000/> : la page liste chaque démo avec une
courte description. Chaque endpoint répond en JSON (sauf la page
d'accueil), lisible directement au navigateur ou via `curl`.

La console affiche aussi la journalisation de `django_goroutine`
(`GOROUTINE` dans `config/settings.py` la configure en `DEBUG`) : on y voit
le démarrage des pools, les timeouts, et les échecs de tâches en direct.

## Ce que chaque vue démontre

- **`/parallel/`** — `group()` combine une tâche `@io` (un appel réseau
  simulé), `@db` (une vraie requête ORM contre le modèle `Article`) et
  `@cpu` (un vrai calcul CPU-bound, un hachage répété). `elapsed_seconds`
  reste proche de la plus lente des trois, pas de leur somme.
- **`/cpu-map/`** — le même calcul de hachage appliqué à 8 entrées via
  `cpu_map()`, réparti sur `GOROUTINE["CPU_POOL_SIZE"]` process.
- **`/timeout/`** — une tâche `@io(timeout=0.05)` qui dort 2 secondes :
  la vue répond presque immédiatement avec `Err(TimeoutError(...))`.
- **`/errors/`** — une tâche `@db` qui lève `Article.DoesNotExist` à côté
  d'une tâche qui réussit : la vue montre que l'échec de l'une n'affecte
  jamais l'autre.
- **`/backpressure/`** — 6 tâches `@db` de 0.2s chacune, avec
  `GOROUTINE["DB_MAX_PENDING"]` volontairement fixé à 2 dans
  `config/settings.py` (au lieu du défaut 4× la taille du pool) : elles ne
  tournent jamais plus de deux à la fois, `elapsed_seconds` tourne donc
  autour de 0.6s plutôt que 0.2s.

## Où regarder le code

- `playground/tasks.py` — les fonctions `@io`/`@db`/`@cpu`, toutes au
  niveau module (contrainte de `cpu_map`/`@cpu` : `ProcessPoolExecutor`
  exige des callables picklables).
- `playground/views.py` — l'orchestration via `group()`/`cpu_map()`, une
  vue par démo.
- `config/settings.py` — la configuration `GOROUTINE` et `LOGGING`
  minimales pour que tout ça tourne et se voie dans la console.

## Ce projet n'est pas un exemple de déploiement en production

Base sqlite locale, `SECRET_KEY` en clair, `DEBUG = True`,
`ALLOWED_HOSTS = ["*"]` : volontairement minimal pour explorer la
librairie en local, pas un modèle de configuration de production — voir
le [README principal](../README.md#limitations-connues) pour ce qui manque
réellement avant un déploiement (PostgreSQL/MySQL, serveur ASGI dédié,
etc.).
