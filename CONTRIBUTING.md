# Contributing to django-goroutine

English · [Français](CONTRIBUTING.fr.md)

Thanks for wanting to contribute! This guide describes how to set up the
development environment and what's expected for a pull request.

## Setup

The project uses [uv](https://docs.astral.sh/uv/) for dependency and
virtual environment management.

```bash
uv sync --group dev
```

## Checks before opening a PR

```bash
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run mypy
uv run pytest --cov=django_goroutine --cov-report=term-missing

# examples/ isn't covered by the pytest suite above (separate Django
# settings): check separately that migrations apply and that each demo
# view still responds after an API change.
uv run python examples/manage.py migrate
```

These same checks run in CI (`.github/workflows/ci.yml`) and must all pass
before a PR is mergeable:

- **ruff**: lint and formatting, including on `examples/`.
- **mypy** (`strict = true`, with `django-stubs`): typing must stay
  precise, including on `Group.go()` (sync/coroutine overloads). Doesn't
  cover `examples/`, excluded from `[tool.mypy] files`.
- **pytest**, against Django 4.2/5.0/5.1/5.2/6.0/6.1 (SQLite). The suite
  covers all three task natures (`io`/`db`/`cpu`), success and failure for
  each, real concurrency (separate threads/processes, measured time gain),
  structural cancellation vs. captured business error, `contextvars`
  propagation, per-task timeout, backpressure, and auto-recovery on a
  broken `@cpu` pool. Coverage is locked at 100%
  (`--cov-fail-under=100`): every new code branch must be tested.
- **examples**: a dedicated CI job applies migrations and checks that each
  demo view responds `200` — any change to the public API must keep
  `examples/` in sync, not just the README.

Tests that exercise `@db` across multiple threads use
`@pytest.mark.django_db(transaction=True)`: pytest-django's default
transactional wrapping isolates each test in an uncommitted transaction on
the main thread, invisible to the pool's other threads/connections —
exactly the problem `@db` is supposed to make safe in production. A test
that writes from several `@db` threads in parallel should read rather than
write to prove parallelization (see
`tests/helpers.read_and_return_thread_name`): sqlite only has a global
write lock and raises `OperationalError("database is locked")` on
concurrent writes, a limitation of the engine, not of the `@db` pool.

If `pre-commit` is installed (`uv run pre-commit install`), ruff and mypy
run automatically before each commit.

## Compatibility

`django-goroutine` targets **Python 3.13+** and **Django 4.2+** (current
LTS and later versions). Any PR must remain compatible with these minimum
versions.

## Code style

- No comment that explains the *what* (the code should be readable on its
  own) — only the *why* when it's non-obvious (hidden constraints,
  undocumented Django/asyncio behavior, a workaround for a known bug).
- No abstraction or feature added beyond what the change requires — in
  particular, no heuristic auto-detection of a task's type (`io`/`db`/
  `cpu`): that decision stays explicit, deliberately, see the dedicated
  section of the README.
- `django_goroutine.decorators` mutates the decorated function in place
  (sets an attribute) rather than returning a wrapper: a function must
  therefore only be decorated once at its definition. A test that reuses
  the same function object to test several decorators must start from a
  fresh copy each time (see
  `tests/test_decorators._make_sync_function`).
- Any function meant for `@cpu`/`cpu_map()` in tests must be defined at
  module level (`tests/helpers.py`), never as a local closure inside a
  test — `ProcessPoolExecutor` fails to pickle a nested function.
- Any new failure path added to `group()`/`cpu_map()` (timeout, broken
  pool...) logs to the `"django_goroutine"` logger, not the root logger
  or `print()` — `DEBUG` for a normal business failure, `INFO` for a
  pool lifecycle event, `WARNING`/`ERROR` for a genuinely abnormal
  condition (timeout, broken pool). See the README's Logging section for
  the per-level detail.

## Commits and PRs

- A clear commit message that explains the *why* of the change.
- One PR = one topic. Prefer several small PRs over a single catch-all PR.
- Describe what changes and how it's tested in the PR description.

## Compatibility and deprecation policy

`django-goroutine` follows [Semantic Versioning](https://semver.org/). The
project is currently in *release candidate* phase (`1.0.0rcN`): the API is
considered frozen but has not yet been battle-tested by real-world usage
outside this repository — see the
[release candidate policy](RELEASING.md#release-candidate-policy-before-the-final-100)
in RELEASING.md for what can/can't change between RCs.

From `1.0.0` onward:

- a **major** (`X.0.0`) can break compatibility;
- a **minor** (`1.X.0`) adds features without breaking anything (for
  example a future `group(cancel_on_error=True)`);
- a **patch** (`1.0.X`) only contains bug fixes.

After `1.0.0`, any deprecated public API keeps working and raises an
explicit `DeprecationWarning` for at least one full minor version before
being removed in a subsequent major.

## Reporting a bug or proposing a feature

Open an [issue](https://github.com/alzeph/django-goroutine/issues) using
the appropriate template. For a security vulnerability, see
[SECURITY.md](SECURITY.md) instead of a public issue.
