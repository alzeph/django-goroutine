from django.db import models


class Article(models.Model):
    """Modèle jouet : juste de quoi donner à `@db` une vraie requête ORM à
    exécuter dans les vues de démonstration."""

    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title
