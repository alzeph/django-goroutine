# Contribuer à django-goroutine

Merci de vouloir contribuer ! Ce guide décrit comment mettre en place
l'environnement de développement et les attentes pour une pull request.

## Mise en place

Le projet utilise [uv](https://docs.astral.sh/uv/) pour la gestion des
dépendances et de l'environnement virtuel.

```bash
uv sync --group dev
```

## Vérifications avant de proposer une PR

```bash
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run mypy
uv run pytest --cov=django_goroutine --cov-report=term-missing

# examples/ n'est pas couvert par la suite pytest ci-dessus (settings
# Django séparés) : vérifier séparément que les migrations s'appliquent et
# que chaque vue de démo répond toujours après un changement d'API.
uv run python examples/manage.py migrate
```

Ces mêmes vérifications tournent dans la CI (`.github/workflows/ci.yml`) et
doivent toutes passer avant qu'une PR soit mergeable :

- **ruff** : lint et formatage, y compris sur `examples/`.
- **mypy** (`strict = true`, avec `django-stubs`) : le typage doit rester
  précis, y compris sur `Group.go()` (overloads sync/coroutine). Ne
  couvre pas `examples/`, exclu de `[tool.mypy] files`.
- **pytest**, contre Django 4.2/5.0/5.1/5.2/6.0/6.1 (SQLite). La suite
  couvre les trois natures de tâche (`io`/`db`/`cpu`), le succès et l'échec
  de chacune, la concurrence réelle (threads/process distincts, gain de
  temps mesuré), l'annulation structurelle vs. l'erreur métier capturée, la
  propagation des `contextvars`, le timeout par tâche, la backpressure, et
  l'auto-récupération sur pool `@cpu` cassé. La couverture est verrouillée
  à 100 % (`--cov-fail-under=100`) : toute nouvelle branche de code doit
  être testée.
- **examples** : un job CI dédié applique les migrations et vérifie que
  chaque vue de démonstration répond `200` — toute modification de l'API
  publique doit garder `examples/` synchronisé, pas seulement le README.

Les tests qui exercent `@db` sur plusieurs threads utilisent
`@pytest.mark.django_db(transaction=True)` : le wrapping transactionnel par
défaut de pytest-django isole chaque test dans une transaction non commitée
sur le thread principal, invisible aux autres threads/connexions du pool —
exactement le problème que `@db` est censé rendre sûr en production. Un
test qui écrit depuis plusieurs threads `@db` en parallèle doit lire
plutôt qu'écrire pour prouver la parallélisation (voir
`tests/helpers.read_and_return_thread_name`) : sqlite n'a qu'un verrou
d'écriture global et lève `OperationalError("database is locked")` sur des
écritures concurrentes, une limite du moteur, pas du pool `@db`.

Si `pre-commit` est installé (`uv run pre-commit install`), ruff et mypy
tournent automatiquement avant chaque commit.

## Compatibilité

`django-goroutine` cible **Python 3.13+** et **Django 4.2+** (LTS courante
et versions suivantes). Toute PR doit rester compatible avec ces versions
minimales.

## Style de code

- Pas de commentaire qui explique le *quoi* (le code doit être lisible par
  lui-même) — seulement le *pourquoi* quand c'est non évident (contraintes
  cachées, comportement Django/asyncio non documenté, contournement d'un
  bug connu).
- Pas d'abstraction ou de fonctionnalité ajoutée au-delà de ce que demande
  le changement — en particulier, pas d'auto-détection heuristique du type
  d'une tâche (`io`/`db`/`cpu`) : cette décision reste explicite,
  volontairement, voir la section dédiée du README.
- `django_goroutine.decorators` mute la fonction décorée en place (pose un
  attribut) plutôt que de retourner un wrapper : une fonction ne doit donc
  être décorée qu'une seule fois à sa définition. Un test qui réutilise le
  même objet fonction pour tester plusieurs décorateurs doit en repartir
  d'une copie fraîche à chaque fois (voir
  `tests/test_decorators._make_sync_function`).
- Toute fonction destinée à `@cpu`/`cpu_map()` dans les tests doit être
  définie au niveau module (`tests/helpers.py`), jamais en closure locale à
  un test — `ProcessPoolExecutor` échoue à picklier une fonction imbriquée.
- Toute nouvelle voie d'échec ajoutée à `group()`/`cpu_map()` (timeout,
  pool cassé...) journalise sur le logger `"django_goroutine"`, pas sur le
  logger racine ni `print()` — `DEBUG` pour un échec métier normal, `INFO`
  pour un événement de cycle de vie d'un pool, `WARNING`/`ERROR` pour une
  condition réellement anormale (timeout, pool cassé). Voir la section
  Journalisation du README pour le détail par niveau.

## Commits et PR

- Un message de commit clair, qui explique le *pourquoi* du changement.
- Une PR = un sujet. Préférer plusieurs petites PR à une seule PR fourre-tout.
- Décrire dans la description de la PR ce qui change et comment c'est testé.

## Politique de compatibilité et dépréciation

`django-goroutine` suit le [Semantic Versioning](https://semver.org/lang/fr/).
Le projet est actuellement en phase de *release candidate* (`1.0.0rcN`) :
l'API est considérée figée mais n'a pas encore été éprouvée par un usage
réel en dehors de ce dépôt — voir la
[politique release candidate](RELEASING.md#politique-release-candidate-avant-le-100-final)
dans RELEASING.md pour ce qui peut/ne peut pas changer d'une RC à l'autre.

À partir de `1.0.0` :

- un **major** (`X.0.0`) peut casser la compatibilité ;
- un **minor** (`1.X.0`) ajoute des fonctionnalités sans rien casser (par
  exemple un futur `group(cancel_on_error=True)`) ;
- un **patch** (`1.0.X`) ne contient que des corrections de bug.

Après `1.0.0`, toute API publique dépréciée continue de fonctionner et lève
un `DeprecationWarning` explicite pendant au moins une version mineure
complète avant d'être retirée dans un major suivant.

## Signaler un bug ou proposer une fonctionnalité

Ouvrez une [issue](https://github.com/alzeph/django-goroutine/issues) en
utilisant le template approprié. Pour une faille de sécurité, voir
[SECURITY.md](SECURITY.md) plutôt qu'une issue publique.
