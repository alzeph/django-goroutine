# Politique de sécurité

[🇬🇧 English](SECURITY.md) · 🇫🇷 Français

## Signaler une vulnérabilité

Merci de ne pas ouvrir d'issue publique pour une faille de sécurité.
Contactez plutôt directement le mainteneur à
[hervecedricyouan@gmail.com](mailto:hervecedricyouan@gmail.com) avec :

- une description du problème et de son impact ;
- les étapes de reproduction ;
- la version de `django-goroutine` concernée.

Une réponse est visée sous 5 jours ouvrés.

## Points d'attention spécifiques à un orchestrateur de concurrence

`django-goroutine` exécute du code applicatif sur des pools de threads et de
process persistants, partagés entre requêtes :

- Une fonction `@db` s'exécute hors du thread de la requête HTTP, mais dans
  le même process, avec le même accès mémoire et la même configuration
  Django (y compris les settings sensibles) — ce n'est pas une sandbox.
- Une fonction `@cpu` s'exécute dans un process séparé
  (`ProcessPoolExecutor`) : ses arguments et son résultat transitent par
  `pickle`. Ne jamais passer à `@cpu`/`cpu_map()` des données provenant
  directement d'une entrée utilisateur non validée en confiant leur
  désérialisation à un code tiers non maîtrisé — le risque n'est pas propre
  à cette librairie, mais au `pickle` inter-process en général.
- Le contexte de requête (utilisateur, langue, session) traverse `group()`
  via `contextvars`/`asgiref`, comme n'importe quel autre `await` Django. Un
  bug dans une fonction `@db`/`@cpu` qui lirait ce contexte pour un mauvais
  utilisateur (fuite de données entre requêtes) est une vulnérabilité de
  sévérité haute et doit être signalé comme telle, pas comme un bug de
  fonctionnalité.
