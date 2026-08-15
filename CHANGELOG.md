# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

## [1.0.0rc1] - 2026-08-15

### Added

- `django_goroutine.group()` : orchestrateur structuré au-dessus
  d'`asyncio.TaskGroup`. `Group.go()` dispatche une tâche décorée `@io`
  (coroutine, exécutée directement sur la boucle d'événements), `@db`
  (fonction sync ORM, dispatchée sur un pool de threads dédié avec
  `asgiref.sync.sync_to_async(thread_sensitive=False)` et nettoyage via
  `close_old_connections`) ou `@cpu` (fonction sync CPU-bound, dispatchée
  sur un `ProcessPoolExecutor` persistant). Chaque tâche renvoie un
  `pycatch.Result` porté par un `TaskHandle` plutôt que de lever — un échec
  métier sur une tâche ne fait jamais planter ses sœurs.
- `django_goroutine.cpu_map()` : parallélise un calcul CPU-bound déjà
  décomposé en unités indépendantes sur le pool de process, avec un
  `Result` par élément (échec partiel n'interrompt pas le lot).
- Décorateurs `django_goroutine.io`/`db`/`cpu` : déclarent uniquement
  *comment* exécuter une fonction, jamais *si* elle doit tourner en
  concurrence — cette décision reste au point d'appel (`Group.go()`), à la
  façon du mot-clé `go` en Go plutôt que d'une coloration figée à la
  définition.
- `django_goroutine.apps.DjangoGoroutineConfig` : démarre le pool de
  threads (`@db`) au boot de l'application plutôt qu'au premier appel. Le
  pool de process (`@cpu`) reste volontairement paresseux — `ready()`
  s'exécute pour n'importe quel process qui charge l'app Django (`migrate`,
  `shell`, `mypy` via django-stubs...), pas seulement un serveur
  applicatif ; spawn systématique de process OS en aurait fait une source
  de fuites de ressources hors contexte serveur.
- Pool `@cpu` construit avec le contexte `multiprocessing` `spawn` plutôt
  que le `fork` par défaut de Linux, pour éviter un blocage classique du
  fork d'un process multi-threadé (boucle asyncio + pool `@db`), et un
  `initializer` qui appelle `django.setup()` dans chaque worker fraîchement
  spawné, pour rester importable même si son module touche à des modèles
  Django.
- Réglages `GOROUTINE["DB_POOL_SIZE"]`/`GOROUTINE["CPU_POOL_SIZE"]`,
  invalidés par `override_settings` comme le reste des projets de l'auteur.
- Propagation automatique des `contextvars` de requête (utilisateur,
  langue...) à travers `group()`, aussi bien pour les tâches `@io` (natif
  `asyncio.Task`) que `@db` (natif `asgiref.sync.sync_to_async`).
- Suite de tests à 100 % de couverture (`--cov-fail-under=100`) et 0
  warning, incluant les scénarios de concurrence réelle (threads/process
  distincts, gain de temps mesuré), d'annulation structurelle (bug dans le
  code appelant vs. erreur métier dans une tâche dispatchée) et de
  contention sqlite (`database is locked` sur écritures concurrentes,
  documentée plutôt que masquée).

### Fixed

- **`close_old_connections()` pouvait fermer la connexion du mauvais
  thread.** Appelée séparément de la fonction `@db` elle-même via deux
  dispatches distincts vers le pool, rien ne garantissait qu'`asgiref` les
  exécute sur le même thread (`django.db.connections` est thread-local).
  Les deux tournent maintenant dans un seul `sync_to_async`, garanties sur
  le même thread.
- **Les tests sqlite pointaient silencieusement vers une base en mémoire
  malgré un `NAME` fichier explicite**, provoquant des connexions jamais
  fermées (`close()` est un no-op volontaire de Django sur une base sqlite
  en mémoire) détectées en `ResourceWarning` fuyant au hasard des tests.
  Django bascule sqlite sur `:memory:` par défaut pour la base de *test*
  quel que soit `NAME`, sauf si `DATABASES["default"]["TEST"]["NAME"]` est
  fixé explicitement.
- **Le pool `@cpu` en contexte `fork` (défaut Linux) pouvait figer un
  worker en CI** sans jamais lever d'erreur explicite — fork d'un process
  multi-threadé (boucle asyncio + pool `@db`) hérite des verrous internes
  potentiellement tenus au moment du fork. Voir plus haut (contexte
  `spawn` + `initializer`).

[Unreleased]: https://github.com/alzeph/django-goroutine/compare/v1.0.0rc1...main
[1.0.0rc1]: https://github.com/alzeph/django-goroutine/commits/v1.0.0rc1
