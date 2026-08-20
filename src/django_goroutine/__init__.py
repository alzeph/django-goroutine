"""django-goroutine : orchestration structurée de tâches concurrentes pour Django.

`group()` (au-dessus d'`asyncio.TaskGroup`) et `cpu_map()` (au-dessus d'un
`ProcessPoolExecutor` persistant), avec des erreurs par tâche renvoyées en
`pycatch.Result` plutôt que levées — inspiré du modèle de concurrence de Go,
adapté aux contraintes réelles de l'ORM Django et du GIL.
"""

from django_goroutine.cpu_map import cpu_map
from django_goroutine.decorators import cpu, db, io
from django_goroutine.group import Group, TaskHandle, group

__version__ = "1.0.0rc2"

__all__ = [
    "Group",
    "TaskHandle",
    "__version__",
    "cpu",
    "cpu_map",
    "db",
    "group",
    "io",
]
