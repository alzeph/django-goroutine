# Release process

English · [Français](RELEASING.fr.md)

This document describes how to publish a new version of
`django-goroutine` to PyPI. It's aimed at anyone with the necessary rights
on the repository (not just the original maintainer): following these
steps in order should be enough, with no implicit project knowledge beyond
what's written here.

## Who can publish

- Write access to the `alzeph/django-goroutine` GitHub repository (to
  create a branch, a tag, and push to `main`).
- Rights to create/approve a
  [GitHub Release](https://github.com/alzeph/django-goroutine/releases). If
  the `pypi` environment (see below) has reviewers configured, their
  approval is required before `publish.yml` runs.
- No personal PyPI account is required to publish once *trusted
  publishing* is configured (see below): authorization goes through OIDC,
  not an individual token.

## Initial PyPI setup (to do before the first publication)

`django-goroutine` publishes via PyPI's *trusted publishing* (OIDC): no
long-lived token to manage, authorization is tied to this exact repository
and this exact GitHub Actions workflow.

1. Create a PyPI account if needed.
2. On <https://pypi.org/manage/account/publishing/>, add a
   *pending trusted publisher* (the project doesn't need to already exist
   on PyPI):
   - PyPI project name: `django-goroutine`
   - Owner: `alzeph`
   - Repository name: `django-goroutine`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. In the repository's GitHub settings (`Settings > Environments`), create
   a `pypi` environment (protects publication, lets you add reviewers if
   needed).

## Publishing a version

### 1. Choose the version number

While the project is in *release candidate* phase (`1.0.0rcN`, the current
situation), see the
[Release candidate policy](#release-candidate-policy-before-the-final-100)
section below to decide whether to bump `N` (`rc1` → `rc2`) or tag the
final `1.0.0`.

Once `1.0.0` is tagged, follow standard
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`) — see the
[Compatibility policy](CONTRIBUTING.md#compatibility-and-deprecation-policy)
section of CONTRIBUTING.md if in doubt about the bump type.

### 2. Prepare a release branch

Don't commit directly to `main`. Create a dedicated branch:

```bash
git checkout -b release/X.Y.Z
```

On this branch:

1. Update `__version__` in `src/django_goroutine/__init__.py` (the
   package version is single-sourced from this file, see
   `[tool.hatch.version]` in `pyproject.toml`).
2. Move the contents of `## [Unreleased]` in `CHANGELOG.md` under a new
   `## [X.Y.Z] - YYYY-MM-DD` section, and update the comparison links at
   the bottom of the file.

### 3. Verify locally

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest --cov=django_goroutine --cov-report=term-missing
uv build
```

All of these commands must pass before continuing. They match exactly what
CI (`.github/workflows/ci.yml`) re-checks on the PR.

### 4. Open a PR and merge

```bash
git add -A
git commit -m "Release X.Y.Z"
git push -u origin release/X.Y.Z
gh pr create --base main --title "Release X.Y.Z" --body "See CHANGELOG.md"
```

Wait for CI to pass on the PR, then merge into `main`.

### 5. Tag

Switch back to an up-to-date `main`, then create an **annotated tag**
(carries a message and an author, unlike a lightweight tag — this is the
standard practice for marking a release):

```bash
git checkout main
git pull origin main
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push origin vX.Y.Z
```

### 6. Create the GitHub Release

Create a [GitHub Release](https://github.com/alzeph/django-goroutine/releases/new)
from the `vX.Y.Z` tag, with release notes taken from `CHANGELOG.md`.
Publishing it triggers `.github/workflows/publish.yml`, which builds and
publishes to PyPI automatically.

- Before `1.0.0`, checking **"Set as a pre-release"** is optional but
  recommended, to signal the lack of an API stability guarantee.
- Then check that the `publish` job in `.github/workflows/publish.yml`
  finishes successfully (`gh run watch` or the repository's Actions tab)
  and that the version appears on
  <https://pypi.org/project/django-goroutine/>.

## Release candidate policy before the final 1.0.0

`1.0.0rc1` (and subsequent RCs, if any) are successive *release
candidates*: the API is considered frozen but has not yet been
battle-tested by real-world usage outside this repository. Before tagging
`1.0.0` (final):

- leave the current RC available for at least a few weeks to gather
  feedback (issues, real use cases, bugs);
- if a bug is found, publish a new RC (`rcN+1`) rather than modifying an
  already-published RC after the fact — each PyPI tag/release is
  immutable;
- an API change between two RCs must be documented in `CHANGELOG.md`
  (`### Changed`/`### Added`/`### Removed` section as appropriate), the RC
  remaining by nature a pre-version with no stability guarantee.

Once `1.0.0` is tagged, see the compatibility policy in
[CONTRIBUTING.md](CONTRIBUTING.md#compatibility-and-deprecation-policy) —
no more breaking changes outside a `MAJOR` bump.
