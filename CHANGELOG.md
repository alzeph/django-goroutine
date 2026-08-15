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
- `django_goroutine.apps.DjangoGoroutineConfig` : démarre les pools de
  threads (`@db`) et de process (`@cpu`) au boot de l'application plutôt
  qu'au premier appel.
- Réglages `GOROUTINE["DB_POOL_SIZE"]`/`GOROUTINE["CPU_POOL_SIZE"]`,
  invalidés par `override_settings` comme le reste des projets de l'auteur.
- Propagation automatique des `contextvars` de requête (utilisateur,
  langue...) à travers `group()`, aussi bien pour les tâches `@io` (natif
  `asyncio.Task`) que `@db` (natif `asgiref.sync.sync_to_async`).
- Suite de tests à 100 % de couverture (`--cov-fail-under=100`), incluant
  les scénarios de concurrence réelle (threads/process distincts, gain de
  temps mesuré), d'annulation structurelle (bug dans le code appelant vs.
  erreur métier dans une tâche dispatchée) et de contention sqlite
  (`database is locked` sur écritures concurrentes, documentée plutôt que
  masquée).

[Unreleased]: https://github.com/alzeph/django-goroutine/compare/v1.0.0rc1...main
[1.0.0rc1]: https://github.com/alzeph/django-goroutine/commits/v1.0.0rc1
