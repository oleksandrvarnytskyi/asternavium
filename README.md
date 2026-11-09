# AsterNavium

Modular platform for astrology, numerology and traditional knowledge systems: deterministic
calculation engines, a structured knowledge base and an AI interpretation layer.

The MVP is an API-first AI chat over Jyotisha and the Slavic symbolic traditions (Bukvitsa).
See [docs/asternavium-mvp-concise-plan.md](docs/asternavium-mvp-concise-plan.md) and the
[detailed specification](docs/asternavium-mvp-specification.md).

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## Getting started

```sh
make install              # uv sync + pre-commit hooks
cp .env.example .env      # then set ASTERNAVIUM_SOURCE_URL
make run                  # http://127.0.0.1:8000/docs
```

## Development

| Command          | What it does                                  |
| ---------------- | --------------------------------------------- |
| `make lint`      | ruff lint and format check                    |
| `make format`    | auto-fix lint issues and format               |
| `make typecheck` | mypy in strict mode                           |
| `make test`      | pytest with coverage                          |
| `make check`     | everything CI runs                            |

Project conventions are in [CLAUDE.md](CLAUDE.md).

## Layout

```
src/app/
├── main.py        # create_app() factory and composition root
├── core/          # settings, JSON logging, errors, request context
├── api/           # /health and versioned routers under /v1
├── data/          # bundled datasets (GeoNames places snapshot)
├── domain/        # pure domain logic: birth data, profile and chat vocabulary
├── repositories/  # persistence and dataset access
├── services/      # use cases: sessions, persons, profile, account deletion
└── schemas/       # Pydantic request/response models
tools/             # developer scripts (local tables, places snapshot)
tests/             # mirrors src/app: api/ and unit/
```

## Licence

AsterNavium is free software under the [GNU AGPL-3.0-or-later](LICENSE); third-party notices
are in [NOTICE](NOTICE). If you run a modified version as a network service, you must offer
its source code to its users. The running service publishes its source URL at
`GET /v1/about`.

Birth place search uses data from [GeoNames](https://www.geonames.org/), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The bundled snapshot in
`src/app/data/places/` is rebuilt with `make places-snapshot`; see [NOTICE](NOTICE) for the
changes made to the data.
