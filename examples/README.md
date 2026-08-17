# django-goroutine — playground

🇬🇧 English · [🇫🇷 Français](README.fr.md)

A minimal Django project for exploring `group()`, `cpu_map()`, timeout,
and backpressure without configuring anything yourself: it runs in the
same virtual environment as the package itself (`django-goroutine` is
already installed there, in editable mode, as soon as you run `uv sync`).

## Run it

From the repository root:

```bash
uv sync --group dev                          # if not already done
uv run python examples/manage.py migrate
uv run python examples/manage.py runserver
```

Then open <http://127.0.0.1:8000/>: the page lists each demo with a short
description. Every endpoint responds in JSON (except the home page),
readable directly in the browser or via `curl`.

The console also shows `django_goroutine` logging (`GOROUTINE` in
`config/settings.py` configures it at `DEBUG`): you'll see pools starting
up, timeouts, and task failures live.

## What each view demonstrates

- **`/parallel/`** — `group()` combines an `@io` task (a simulated network
  call), a `@db` task (a real ORM query against the `Article` model), and a
  `@cpu` task (a real CPU-bound computation, a repeated hash).
  `elapsed_seconds` stays close to the slowest of the three, not their sum.
- **`/cpu-map/`** — the same hash computation applied to 8 inputs via
  `cpu_map()`, spread across `GOROUTINE["CPU_POOL_SIZE"]` processes.
- **`/timeout/`** — an `@io(timeout=0.05)` task that sleeps for 2 seconds:
  the view responds almost immediately with `Err(TimeoutError(...))`.
- **`/errors/`** — a `@db` task that raises `Article.DoesNotExist` next to
  a task that succeeds: the view shows that one's failure never affects
  the other.
- **`/backpressure/`** — 6 `@db` tasks of 0.2s each, with
  `GOROUTINE["DB_MAX_PENDING"]` deliberately set to 2 in
  `config/settings.py` (instead of the default 4× the pool size): they
  never run more than two at a time, so `elapsed_seconds` hovers around
  0.6s rather than 0.2s.

## Where to look at the code

- `playground/tasks.py` — the `@io`/`@db`/`@cpu` functions, all at module
  level (a constraint of `cpu_map`/`@cpu`: `ProcessPoolExecutor` requires
  picklable callables).
- `playground/views.py` — the orchestration via `group()`/`cpu_map()`, one
  view per demo.
- `config/settings.py` — the minimal `GOROUTINE` and `LOGGING`
  configuration needed for all of this to run and be visible in the
  console.

## This project is not a production deployment example

Local sqlite database, `SECRET_KEY` in plaintext, `DEBUG = True`,
`ALLOWED_HOSTS = ["*"]`: deliberately minimal to explore the library
locally, not a production configuration template — see the
[main README](../README.md#known-limitations) for what's actually missing
before a deployment (PostgreSQL/MySQL, a dedicated ASGI server, etc.).
