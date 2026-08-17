# django-goroutine

🇬🇧 English · [🇫🇷 Français](README.fr.md)

[![CI](https://github.com/alzeph/django-goroutine/actions/workflows/ci.yml/badge.svg)](https://github.com/alzeph/django-goroutine/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/django-goroutine.svg)](https://pypi.org/project/django-goroutine/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](pyproject.toml)

> **Release candidate.** `django-goroutine` is at `1.0.0rc1`: the API is
> considered frozen but has not yet been battle-tested by real-world usage
> outside this repository. Feedback (issues, use cases, bugs) is welcome
> before the final `1.0.0` is tagged — see [RELEASING.md](RELEASING.md).

A structured concurrent-task orchestrator for Django, inspired by Go's
concurrency model — without pretending to reproduce it identically.

## The problem

Django can run views and ORM methods with `async`/`await`, but it gives you
no off-the-shelf tool for launching several independent operations in
parallel inside a view. Rolling your own with `asyncio.gather` quickly runs
into three obstacles: the ORM's connection pool (historically sync), which
misbehaves across multiple threads; request context (user, language,
session), which doesn't always propagate cleanly; and a dozen lines of
plumbing to cancel/clean up if a subtask fails. `django-goroutine` provides
`group()` (built on top of `asyncio.TaskGroup`) and `cpu_map()` (built on
top of a persistent `ProcessPoolExecutor`) to cover these three obstacles,
with per-task errors returned as
[`pycatch.Result`](https://pypi.org/project/pycatch-safe/) rather than
raised.

## What "goroutine" doesn't mean here

A Go goroutine is a green thread managed by the runtime, able to migrate
between OS threads. Python keeps a single, cooperative event loop:
`group()` doesn't replicate that model, it borrows its spirit — the call
site decides what to run concurrently, not the function itself — with
three distinct ways to run a task depending on its actual nature:

| Decorator | Nature of the task | Runs on |
|---|---|---|
| `@io` (or an undecorated coroutine) | Network/disk wait (`async def`) | The event loop, no dedicated thread or process |
| `@db` | Blocking sync ORM call | The dedicated thread pool (`GOROUTINE["DB_POOL_SIZE"]`) |
| `@cpu` | Sync CPU-bound computation | The dedicated process pool (`GOROUTINE["CPU_POOL_SIZE"]`) |

This explicit choice, rather than automatic detection, is deliberate: a
heuristic (timing, introspection) for guessing a function's nature would be
unreliable and would reproduce exactly the kind of sneaky bugs this project
is trying to avoid.

## Installation

```bash
uv add django-goroutine
pip install django-goroutine
```

Since a release candidate isn't a final version, PyPI doesn't install it by
default with `pip install django-goroutine` — use `--pre` or pin the exact
version until `1.0.0` is tagged:

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

`ready()` starts the thread pool (`@db`) at boot rather than on first call,
so its creation cost isn't paid on the first request that uses it. The
process pool (`@cpu`) stays deliberately lazy (created on the first actual
call) — see the Known limitations section.

## Quick start

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

`fetch_user` and `fetch_avatar` run in parallel: the view's response time
drops to the time of the slower of the two, not their sum.

To see all of this running without configuring anything yourself, see
[`examples/`](examples/): a minimal Django project with views that
demonstrate `group()`, `cpu_map()`, timeout, and backpressure, launchable
with a single command from this repository.

### Inheritance of internal calls

A function called *from* `fetch_user` (an internal helper, a second ORM
call) simply runs in the same call stack, on the same thread — no further
decoration is needed or useful. The decorator only matters at the moment
`Group.go()` dispatches the task, not for internal call propagation.

### Per-task errors, no cascading cancellation on business errors

Any exception raised by a dispatched task becomes an `Err` carried by its
`TaskHandle`: it never crashes sibling tasks or the enclosing block —
`group()` is a `sync.WaitGroup`, not an `errgroup` with automatic
cancellation on business error. Cancellation is still possible, but only
structurally: if the `async with group()` block itself is cancelled from
the outside (ASGI server timeout, client disconnect), the tasks still in
flight are cancelled by `asyncio.TaskGroup`, like any other `await`.

```python
async with group() as g:
    a = g.go(fetch_user, user_id)      # fails
    b = g.go(fetch_avatar, avatar_url) # keeps running regardless, not cancelled

a.result()  # Err(UserDoesNotExist(...))
b.result()  # Ok(b"...")
```

`TaskHandle.result()` can only be read once the `async with group()` block
has closed — calling it before that raises `RuntimeError`.

### Per-task timeout

A default timeout can't be set on `Group.go()` itself (its `*args`/
`**kwargs` are already reserved for forwarding to the decorated function),
so `@io`/`@db`/`@cpu` are used bare or parameterized:

```python
@db(timeout=2.0)
def fetch_user(user_id: int) -> User:
    return User.objects.get(pk=user_id)
```

Past `timeout` seconds, `TaskHandle.result()` becomes
`Err(TimeoutError(...))` — without crashing sibling tasks, like any other
failure. `GOROUTINE["TASK_TIMEOUT"]` sets a default value for tasks that
don't specify their own (`None` by default, so no timeout at all until
something is configured). An important caveat to know: Python cannot
forcibly interrupt a thread or process already running the task — past the
timeout, the caller stops waiting and gets its `Err` back, but the
thread/process keeps executing the task in the background until it
naturally finishes.

### Backpressure

The number of `@db`/`@cpu` tasks simultaneously queued or in flight is
bounded (`GOROUTINE["DB_MAX_PENDING"]`/`CPU_MAX_PENDING`, defaulting to 4×
the size of the corresponding pool): beyond that, a new call waits for a
slot to free up instead of piling up without limit in the executor's
internal queue — this is what keeps a load spike from blowing up memory or
latency instead of failing or waiting cleanly. This combines naturally with
`timeout`, which then bounds both the wait for a free slot *and* the
execution itself.

### `@cpu` pool auto-recovery

If a `@cpu` pool worker crashes hard (segfault, `os._exit`...), the whole
pool becomes unusable (`BrokenProcessPool`) until it's recreated.
`django-goroutine` detects this case and resets the pool automatically: the
call in flight fails (`Err(BrokenProcessPool(...))`, no automatic retry —
replaying a function that may already have had side effects would be
worse), but subsequent calls get a healthy pool back instead of staying
broken indefinitely.

## Parallelizing a CPU-bound computation (`cpu_map`)

`@cpu` on `group().go()` only saves time on work already split into
independent units. A single CPU-bound function dispatched alone doesn't
speed anything up — exactly like a single Go goroutine doesn't speed up a
monolithic computation: the gain always comes from splitting into
independent units spread across several cores, never from the
orchestration tool itself. `cpu_map()` covers the case where that split
already exists:

```python
from django_goroutine import cpu_map


def resize_one(image_bytes: bytes) -> bytes:
    ...


async def batch_resize_view(request, images):
    results = await cpu_map(resize_one, images)
    ...
```

`fn` must be a sync CPU-bound function, importable at module level (a
`pickle` constraint of the underlying `ProcessPoolExecutor`) — never a
lambda, a closure, or a bound instance method. A failure on one element,
including a `timeout` overrun (seconds, optional, applied individually to
each element — `cpu_map(fn, items, timeout=5.0)`) or a broken `@cpu` pool
(auto-reset), doesn't fail the others: each result is an independent
`Result`, in input order. `cpu_map()` shares the same backpressure
semaphore as `group()`'s `@cpu` tasks — both compete for the same
resource.

The GIL prevents two threads from executing Python bytecode in parallel: if
your heavy computation already goes through a C library that releases the
GIL (numpy, Pillow, OpenCV, hashlib...), `@db`-style thread offload would
be enough — `@cpu`/`cpu_map()` only bring a real gain for pure CPU-bound
Python code, via separate processes.

## Configuration

```python
GOROUTINE = {
    "DB_POOL_SIZE": 10,                # @db thread pool size
    "CPU_POOL_SIZE": os.cpu_count(),   # @cpu process pool size
    "DB_MAX_PENDING": None,            # @db backpressure; None => DB_POOL_SIZE * 4
    "CPU_MAX_PENDING": None,           # @cpu/cpu_map backpressure; None => CPU_POOL_SIZE * 4
    "TASK_TIMEOUT": None,              # default timeout (seconds); None => none
}
```

## Logging

All task and pool events go through the Python logger
`"django_goroutine"`, to be wired up like any other Django logger:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django_goroutine": {"handlers": ["console"], "level": "INFO"},
    },
}
```

| Level | Emitted for |
|---|---|
| `DEBUG` | An `@io`/`@db`/`@cpu`/`cpu_map()` task fails with a business exception (normal case, handled via `Result` — no noise by default). |
| `INFO` | A pool starting up (`@db` at boot, `@cpu` on first call). |
| `WARNING` | A task exceeds its `timeout`. |
| `ERROR` | The `@cpu` pool is broken (`BrokenProcessPool`) and resets. |

Without an explicit `LOGGING` configuration, Django already logs `WARNING`
and above to the console via its default root handler — only `DEBUG`
requires explicit configuration to become visible.

## Known limitations

- **sqlite and concurrent writes.** sqlite only has a global write lock:
  several `@db` functions writing in parallel against a sqlite database can
  raise `OperationalError("database is locked")`. PostgreSQL and MySQL
  absorb concurrent writes without this lock — in development with sqlite,
  increase `OPTIONS.timeout` or avoid concurrent writes on the same pool.
- **The `@cpu` pool is lazy, not started by `apps.ready()`.** Two reasons,
  not a matter of taste: `ready()` runs for any process that loads the
  Django app — `migrate`, `shell`, or even `mypy` via the django-stubs
  plugin, which really does call `django.setup()` — not just an
  application server; spawning OS processes every time would have made it
  a source of resource leaks on commands that never use `@cpu`. And
  starting a `ProcessPoolExecutor` before a fork (gunicorn `--preload`) is
  a known source of `multiprocessing` deadlocks — lazy creation eliminates
  this risk along the way, the pool being created in each worker after the
  fork, not before. The pool also uses the `spawn` multiprocessing context
  rather than Linux's default `fork`: forking a multi-threaded process
  (asyncio loop + `@db` pool) can freeze the child if a thread held an
  internal lock at fork time — `spawn` starts a fresh interpreter, slower
  on the first call but without that inheritance. Each `spawn` worker calls
  `django.setup()` on startup (via the pool's `initializer`) so it stays
  importable even if its module touches, even indirectly, Django models.
- **No automatic cancellation of sibling tasks on business error.**
  `group()` is deliberately a `sync.WaitGroup`, not an `errgroup` with
  cancellation on first failure — see the dedicated section above. A
  `cancel_on_error` mode could be added in a future minor version if the
  need is confirmed by usage.
- **`@cpu`/`cpu_map()` require module-level picklable functions.** A
  constraint of `ProcessPoolExecutor`, not of this project — a lambda, a
  closure, or a bound method silently fail to be pickled.

## Development

```bash
uv sync --group dev

uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest --cov=django_goroutine --cov-report=term-missing
```

See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute,
[CHANGELOG.md](CHANGELOG.md) for the version history, and
[RELEASING.md](RELEASING.md) for the release process.

## License

[MIT](LICENSE)
