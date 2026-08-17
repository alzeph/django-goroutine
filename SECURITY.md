# Security policy

English · [Français](SECURITY.fr.md)

## Reporting a vulnerability

Please don't open a public issue for a security vulnerability. Instead,
contact the maintainer directly at
[hervecedricyouan@gmail.com](mailto:hervecedricyouan@gmail.com) with:

- a description of the problem and its impact;
- reproduction steps;
- the affected `django-goroutine` version.

A response is targeted within 5 business days.

## Points of attention specific to a concurrency orchestrator

`django-goroutine` runs application code on persistent thread and process
pools, shared across requests:

- A `@db` function runs outside the HTTP request's thread, but in the same
  process, with the same memory access and the same Django configuration
  (including sensitive settings) — this is not a sandbox.
- A `@cpu` function runs in a separate process (`ProcessPoolExecutor`): its
  arguments and result go through `pickle`. Never pass to `@cpu`/
  `cpu_map()` data coming directly from unvalidated user input while
  trusting its deserialization to unaudited third-party code — the risk
  isn't specific to this library, but to inter-process `pickle` in
  general.
- Request context (user, language, session) travels through `group()` via
  `contextvars`/`asgiref`, like any other Django `await`. A bug in a
  `@db`/`@cpu` function that reads this context for the wrong user (data
  leak between requests) is a high-severity vulnerability and should be
  reported as such, not as a feature bug.
