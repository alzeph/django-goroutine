# Changelog

English · [Français](CHANGELOG.fr.md)

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0rc2] - 2026-08-20

### Fixed

- **`DB_MAX_PENDING`/`CPU_MAX_PENDING` set explicitly to `0` was silently
  ignored.** `get_db_semaphore()`/`get_cpu_semaphore()` computed the
  backpressure limit with `app_settings.DB_MAX_PENDING or POOL_SIZE * 4`:
  since `0` is falsy in Python, an explicit `0` fell back to the computed
  default instead of being honored, unlike every other optional
  `GOROUTINE` setting (which all use an explicit `is None` check). Now
  `0` is respected like any other explicit value.
- **CI jobs had no `timeout-minutes`.** A regression of the kind described
  in the project's `fork`/`spawn` postmortem (a job stuck `in_progress`
  with no error, no advancing log) would have run until GitHub Actions'
  default 6-hour job timeout instead of failing fast. Every job in
  `ci.yml` now caps at 10 minutes.

### Documented

- **`@cpu` pool crashes aren't fully isolated to the failing task.**
  `ProcessPoolExecutor` marks every task still queued or in flight on a
  pool as `Err(BrokenProcessPool(...))` when one worker crashes hard, not
  only the task whose worker actually died — a healthy sibling `@cpu` task
  running at the same moment can be collateral damage. This is a
  `ProcessPoolExecutor` characteristic that `django-goroutine` cannot
  isolate away without giving up a pool shared across calls; `@io`/`@db`
  tasks are unaffected. Documented in the `@cpu` pool auto-recovery and
  Known limitations sections of the README (previously undocumented
  behavior, not a change in behavior).

## [1.0.0rc1] - 2026-08-15

### Added

- `django_goroutine.group()`: a structured orchestrator on top of
  `asyncio.TaskGroup`. `Group.go()` dispatches a task decorated `@io`
  (coroutine, run directly on the event loop), `@db` (blocking sync ORM
  function, dispatched to a dedicated thread pool with
  `asgiref.sync.sync_to_async(thread_sensitive=False)` and cleanup via
  `close_old_connections`), or `@cpu` (sync CPU-bound function, dispatched
  to a persistent `ProcessPoolExecutor`). Each task returns a
  `pycatch.Result` carried by a `TaskHandle` instead of raising — a
  business failure on one task never crashes its siblings.
- `django_goroutine.cpu_map()`: parallelizes a CPU-bound computation
  already broken into independent units on the process pool, with one
  `Result` per element (a partial failure doesn't interrupt the batch).
- `django_goroutine.io`/`db`/`cpu` decorators: they only declare *how* to
  run a function, never *whether* it should run concurrently — that
  decision stays at the call site (`Group.go()`), in the spirit of Go's
  `go` keyword rather than a coloring fixed at definition time.
- `django_goroutine.apps.DjangoGoroutineConfig`: starts the thread pool
  (`@db`) at application boot rather than on first call. The process pool
  (`@cpu`) stays deliberately lazy — `ready()` runs for any process that
  loads the Django app (`migrate`, `shell`, `mypy` via django-stubs...),
  not just an application server; systematically spawning OS processes
  would have made it a source of resource leaks outside a server context.
- `@cpu` pool built with the `spawn` multiprocessing context rather than
  Linux's default `fork`, to avoid a classic deadlock when forking a
  multi-threaded process (asyncio loop + `@db` pool), and an `initializer`
  that calls `django.setup()` in each freshly spawned worker, so it stays
  importable even if its module touches Django models.
- `GOROUTINE["DB_POOL_SIZE"]`/`GOROUTINE["CPU_POOL_SIZE"]` settings,
  overridable via `override_settings` like the rest of the author's
  projects.
- Automatic propagation of request `contextvars` (user, language...)
  through `group()`, both for `@io` tasks (native `asyncio.Task`) and
  `@db` tasks (native `asgiref.sync.sync_to_async`).
- Per-task timeout: `@io`/`@db`/`@cpu` are used bare or parameterized
  (`@db(timeout=2.0)`), with an optional global default
  (`GOROUTINE["TASK_TIMEOUT"]`). An overrun becomes
  `Err(TimeoutError(...))` without crashing sibling tasks. `cpu_map()`
  accepts the same `timeout`, applied individually to each element.
- Backpressure on the `@db`/`@cpu` pools: the number of tasks
  simultaneously queued or in flight is bounded
  (`GOROUTINE["DB_MAX_PENDING"]`/`CPU_MAX_PENDING`, defaulting to 4× the
  pool size), via an `asyncio.Semaphore` shared between `group()` and
  `cpu_map()` — beyond that, a new call waits for a slot to free up instead
  of piling up without limit in the executor's internal queue.
- `@cpu` pool auto-recovery on `BrokenProcessPool` (a worker that crashed
  hard): the task in flight fails, but the pool is reset for subsequent
  calls instead of staying broken indefinitely. Same handling in
  `group()` and `cpu_map()`.
- Clean pool shutdown registered via `atexit` at app startup
  (`DjangoGoroutineConfig.ready()`) — no configuration needed on the
  project side, given the absence of a generic application-shutdown signal
  in Django for a reusable app.
- Default logging on the `"django_goroutine"` logger: `DEBUG` for a
  business failure on a task, `INFO` when a pool starts, `WARNING` on a
  timeout overrun, `ERROR` on a broken `@cpu` pool.
- [`examples/`](examples/) folder: a minimal Django project demonstrating
  `group()`/`cpu_map()`/timeout/backpressure, launchable directly from the
  repository's venv with no extra configuration or dependency.
- Test suite at 100% coverage (`--cov-fail-under=100`) and 0 warnings,
  including real concurrency scenarios (separate threads/processes,
  measured time gain), structural cancellation (bug in the calling code vs.
  business error in a dispatched task), sqlite contention
  (`database is locked` on concurrent writes, documented rather than
  hidden), timeout, backpressure (measured serialization past
  `MAX_PENDING`), and auto-recovery on a broken `@cpu` pool (worker crash
  simulated via `os._exit`).

### Fixed

- **`close_old_connections()` could close the wrong thread's
  connection.** Called separately from the `@db` function itself via two
  distinct dispatches to the pool, nothing guaranteed `asgiref` would run
  them on the same thread (`django.db.connections` is thread-local). Both
  now run inside a single `sync_to_async`, guaranteed on the same thread.
- **sqlite tests were silently pointing at an in-memory database despite
  an explicit file `NAME`**, causing connections that never closed
  (`close()` is a deliberate no-op in Django on an in-memory sqlite
  database) detected as `ResourceWarning` leaking at random across tests.
  Django switches sqlite to `:memory:` by default for the *test* database
  regardless of `NAME`, unless
  `DATABASES["default"]["TEST"]["NAME"]` is set explicitly.
- **The `@cpu` pool in `fork` context (Linux default) could freeze a
  worker in CI** without ever raising an explicit error — forking a
  multi-threaded process (asyncio loop + `@db` pool) inherits internal
  locks potentially held at fork time. See above (`spawn` context +
  `initializer`).

[Unreleased]: https://github.com/alzeph/django-goroutine/compare/v1.0.0rc2...main
[1.0.0rc2]: https://github.com/alzeph/django-goroutine/compare/v1.0.0rc1...v1.0.0rc2
[1.0.0rc1]: https://github.com/alzeph/django-goroutine/commits/v1.0.0rc1
