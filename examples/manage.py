#!/usr/bin/env python
"""Point d'entrée du projet de démonstration — voir examples/README.md."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django est introuvable. Depuis la racine du dépôt : "
            "`uv sync --group dev`, puis relancer cette commande via `uv run`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
