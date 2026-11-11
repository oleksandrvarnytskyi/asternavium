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

Until Phase 4 the API runs on your machine and keeps its data in a DynamoDB table in your own
AWS account (`eu-central-1` by default). Tests never call AWS: they run against moto.

```sh
make install                  # uv sync + pre-commit hooks
cp .env.example .env          # then set ASTERNAVIUM_SOURCE_URL
export AWS_PROFILE=<profile>  # an AWS profile with DynamoDB access in the region
make local-tables             # create the asternavium-local-app table; safe to repeat
make run                      # http://127.0.0.1:8000/docs
```

`AWS_PROFILE` goes in your shell, not in `.env`: the app reads only `ASTERNAVIUM_` settings,
and credentials always come from the standard AWS chain. The table is on-demand, so local use
costs at most a few cents.

### Dev identity

Until real login arrives in Phase 5, the caller is whoever the `X-Dev-User` header names: any
user ID of 1 to 64 letters, digits, `-` and `_`. The header is accepted only when
`ASTERNAVIUM_ENVIRONMENT=dev`. In Swagger UI, click **Authorize** and enter a user ID such as
`alice`; authorize as `bob` to check that Alice's data is invisible to him.

```sh
curl -H "X-Dev-User: alice" "http://127.0.0.1:8000/v1/places?query=kyiv"
```

A typical first run: find the birthplace with `GET /v1/places`, add a person with
`POST /v1/persons` using its `place_id`, mark that person as you with `PUT /v1/profile`
(`owner_person_id`), read it back with `GET /v1/me`, then create and list sessions under
`/v1/sessions`.

### Resetting local data

- One user: `DELETE /v1/me` as that user removes their profile, persons, sessions and messages.
- Everything: `make local-tables-delete && make local-tables` drops and recreates the table.
  The script touches only tables whose names start with `asternavium-local-`.

### Refreshing the places snapshot

Birthplace search reads the GeoNames snapshot bundled in `src/app/data/places/`. To refresh
it, run `make places-snapshot` (downloads about 14 MB) and commit both output files. Saved
persons keep the place values they were saved with, so a refresh never changes them.

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
