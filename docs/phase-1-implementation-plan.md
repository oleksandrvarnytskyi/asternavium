# Phase 1 Implementation Plan: Data Layer and Sessions (Local)

Oct 29, 2026

This plan breaks Phase 1 of the MVP into ordered, verifiable steps. Scope and exit criteria come from the concise plan (`asternavium-mvp-concise-plan.md`, section 3) and the detailed specification (`asternavium-mvp-specification.md`, sections 4 to 7 and 12). Phase 1 runs locally: the app uses a personal AWS account only for its DynamoDB table, and tests never call AWS. Chat, the LLM and the checkpoints table arrive in Phase 2.

## 1. Goal and exit criterion

Phase 1 gives the API persistent users, profiles and chat sessions, so that Phase 2 can attach the agent to them.

**Done when:** sessions can be created and listed per test user, and cross-user access returns `404`.

Concretely, all of the following hold:

1. Through Swagger UI at `http://127.0.0.1:8000/docs`, with the dev identity set in the Authorize dialog, a test user can create, list, rename and delete sessions, read a session's message history, update their profile with `PUT /v1/profile`, and read it back with `GET /v1/me`.
2. A second test user cannot see, rename, delete or read the messages of the first user's sessions; every such request returns `404`, so a session's existence is not revealed.
3. Deleting the account removes the profile, all sessions and all their messages.
4. The running app stores its data in the `asternavium-local-app` table in the personal AWS account (`eu-central-1`), created by a script in the repository.
5. `make check` passes without AWS credentials or network: DynamoDB code is tested against moto.
6. Without `ASTERNAVIUM_ENVIRONMENT=dev`, the dev identity is rejected, and a test proves it.
7. Birth data is never logged, never echoed in error messages, and only synthetic birth data appears in tests.
8. The user gives the birth place by name only: `GET /v1/places` finds it in a bundled GeoNames dataset, the user picks one result, and the server fills in coordinates and time zone. No birth place is sent to an external service.

## 2. Starting point

| Item | Status |
| --- | --- |
| App factory, settings, JSON logging, error model, request IDs, `/health`, `/v1/about`, licence files, CI | Done in Phase 0 |
| AWS profile `savar` (personal account, access keys) | Exists; needs only DynamoDB access in `eu-central-1` for this phase |
| DynamoDB dependency, repositories, sessions and profile endpoints, dev identity, places dataset and search | To do |

## 3. Decisions

The specification fixes the data model (section 7), the endpoints (section 5) and the ownership rule (section 6). The points below are not settled there; all are decided.

| # | Decision | Choice | Why |
| --- | --- | --- | --- |
| D1 | How sessions are created in Phase 1 | Add a temporary `POST /v1/sessions` (module, optional title), removed in Phase 2 once `POST /v1/chat` creates sessions (decided) | The specification creates sessions only implicitly in `POST /v1/chat`, which exists from Phase 2, so without this endpoint nothing in the API can create a session to list, rename or delete, and the exit criterion cannot be shown in Swagger UI. It is a thin wrapper over `SessionService.create`, which Phase 2 reuses. Removing it in Phase 2 leaves one creation path and avoids empty sessions using up the Free plan's session limit. No client depends on it, and the removal is listed in Phase 2 of the specification |
| D2 | Reading the profile | Introduce `GET /v1/me` now, returning the user ID and profile; plan, entitlements and quota fields are added in Phases 5 and 6 (decided) | One endpoint instead of two with overlapping data, and no endpoint beyond the specification. Adding fields later does not break clients. `profile` is `null` until the first `PUT /v1/profile`, because the user exists without a profile |
| D3 | Account deletion endpoint | `DELETE /v1/me` (decided) | Section 7 requires account deletion, but section 5 names no endpoint. `/v1/me` is the account resource in the specification |
| D4 | Repositories built now | Profile, session and message only (decided) | The specification also lists subscription and quota repositories for this phase; nothing uses them before Phase 6, so building them now is speculative (CLAUDE.md: no unused abstractions) |
| D5 | Stripe customer GSI | Add in Phase 6 (decided) | DynamoDB adds a GSI to an existing table without downtime or migration; nothing queries it before Phase 6 |
| D6 | Async access to DynamoDB | `boto3` behind async repository methods, run in a worker thread (`anyio.to_thread`) (decided) | CLAUDE.md requires async I/O that never blocks the event loop. `aioboto3` is async-native, but moto's in-process mock and `langgraph-checkpoint-aws` (Phase 2) are built on `boto3`; the checkpointer's async methods run its synchronous `boto3` calls in a thread pool, the same pattern chosen here. One client library keeps tests and the checkpointer simple |
| D7 | Birth place input | The user gives only a place name. `GET /v1/places` searches a GeoNames city dataset bundled with the app (places with at least 500 inhabitants, each with coordinates and an IANA time zone); the user picks one result, and `PUT /v1/profile` stores its place ID. The server fills in coordinates and time zone (decided) | The user is never asked for coordinates or a time zone, and nothing is guessed for ambiguous names (Paris, France and Paris, Texas). The lookup runs offline, so birthplaces never leave the system, and results are deterministic and testable. Very small villages are missing; the user picks the nearest town, a few kilometres off. GeoNames data is CC-BY 4.0, attributed in `NOTICE` |
| D8 | Ambiguous and nonexistent local times (DST changes) | Reject nonexistent times; for ambiguous times, require the client to choose the earlier or later instant (decided) | CLAUDE.md requires explicit handling of historical time zone and DST changes; guessing silently would shift a chart by an hour |
| D9 | Birth data and time | Every profile requires birth data, including the birth time to the minute; `PUT /v1/profile` without them is rejected with `invalid_birth_data` (decided) | Jyotisha calculations need the exact birth time, so a profile without full birth data is of no use. Until the first successful `PUT`, `GET /v1/me` returns `profile: null` |
| D10 | Pagination order | Newest first, with an opaque cursor; default page size 20, maximum 50 (decided) | Matches the ULID sort keys (a plain `Query` with descending order); the client reverses a history page for display |

## 4. Data model

The single-table design from section 7 of the specification, limited to what Phase 1 uses. Every key is built in one module, so key formats exist in one place.

| Item | PK | SK | Attributes |
| --- | --- | --- | --- |
| Profile | `USER#<user_id>` | `PROFILE` | birth data (required), locale (BCP 47, default `en`), preferred tradition (`jyotisha`, `bukvitsa`; default `jyotisha`), answer depth (`essentials`, `detailed`, `technical`; default `essentials`), created and updated timestamps |
| Session | `USER#<user_id>` | `SESSION#<ulid>` | title, module, message count, created and updated timestamps |
| Message | `SESSION#<ulid>` | `MSG#<ulid>` | role, content, created timestamp; token counts, model and trace ID are added in Phase 2 |

Birth data is stored as: the local date, the local time (to the minute), the ambiguity choice where it applied, the GeoNames place ID with its display name, region and country (so places with the same name, such as Paris in France and in Texas, stay distinguishable), latitude, longitude and IANA time zone copied from the dataset at save time, the dataset version, and the UTC instant computed from them. Copying the place values means a later dataset refresh never changes a saved profile silently. Keeping both the original local values and the UTC instant follows the CLAUDE.md time rules and lets a later change in time zone data be corrected.

The table has `PK` and `SK` as string keys, on-demand capacity, and TTL on an `expires_at` attribute (unused until the quota items in Phase 6). The table definition lives in one place in the app; the local table script and the moto test fixtures both use it, and the Terraform `data` module in Phase 4 must match it.

## 5. API

All endpoints are under `/v1`, require the dev identity in this phase, and return the shared error model on failure.

| Method, path | Purpose | Notes |
| --- | --- | --- |
| `GET /v1/places` | Search birthplaces by name | Query: `query` (2 to 100 characters), `limit` (default 10). Returns place ID, name, region, country and time zone, largest population first; no coordinates needed by the client. Decision D7 |
| `POST /v1/sessions` | Create a session | Body: `module` (`jyotisha`, `bukvitsa`, `general`), optional `title` (default "New chat", at most 100 characters). Temporary, removed in Phase 2. Decision D1 |
| `GET /v1/sessions` | List own sessions, newest first | Query: `limit`, `cursor` |
| `GET /v1/sessions/{id}/messages` | One session's history, newest first | Query: `limit`, `cursor`. Empty until Phase 2 writes messages |
| `PATCH /v1/sessions/{id}` | Rename | Body: `title` |
| `DELETE /v1/sessions/{id}` | Delete the session and its messages | `204`; idempotent. An ID the caller has no session with also returns `204` and changes nothing, since a repeat delete by the owner cannot be told apart from another user's ID |
| `GET /v1/me` | Read the current user | User ID and profile; `profile` is `null` until the first `PUT`. Plan, entitlements and quota are added in Phases 5 and 6. Decision D2 |
| `PUT /v1/profile` | Create or replace own profile | Birth date, birth time and place ID from `GET /v1/places` (all required), ambiguity choice if needed; locale, tradition, answer depth |
| `DELETE /v1/me` | Delete the account and all its data | `204`; idempotent. Decision D3 |

Ownership is enforced by the key design: a session is always read with the caller's `USER#<user_id>` partition key, so another user's session ID simply does not exist for them and returns `404` (`session_not_found`). Message history is read only after that ownership check.

## 6. Work breakdown

The steps run in order; within a step, items can be done in any order. Each step says how to check that it is done.

### Step 1. Confirm decisions and update the specification

1. Decisions D1 to D10 in section 3 are confirmed.
2. Add the confirmed endpoints (`GET /v1/places`, `DELETE /v1/me`) to the API table in section 5 of the specification; list the temporary `POST /v1/sessions` in the specification's Phase 1 and its removal in Phase 2 instead, since it is not part of the final API; record the bundled GeoNames dataset for birthplaces (the specification currently leaves birth-place lookup to the production web client), note that `GET /v1/me` arrives in Phase 1 with the profile and grows in Phases 5 and 6, and note that the subscription and quota repositories and the Stripe GSI move to Phase 6.

**Done when:** the specification and this plan agree.

### Step 2. Dependencies and settings

1. Add runtime dependencies: `boto3` (Apache-2.0), `python-ulid` (MIT) and `tzdata` (Apache-2.0), so the IANA time zone database is the same on macOS, Linux and Lambda and knows every zone name in the GeoNames data. Add development dependencies: `moto[dynamodb]` (Apache-2.0), `boto3-stubs[dynamodb]` (MIT) for `mypy --strict`, and `hypothesis` (MPL-2.0, used only in tests). Record each licence before adding it, and add the runtime ones to `NOTICE`.
2. Extend `Settings`: `aws_region` (default `eu-central-1`) and `app_table_name` (`asternavium-local-app` in `.env.example`). AWS credentials are not settings: `boto3` reads `AWS_PROFILE=savar` from the environment, set in the shell or the PyCharm run configuration, never in the repository.
3. Create the DynamoDB client once in the composition root (`create_app`) and pass it to the repositories, so tests can supply a moto-backed client.

**Done when:** `make check` passes and `create_app` builds the client from settings.

### Step 3. Table definition and local table script

1. Define the table (keys, billing mode, TTL) in one module of the app.
2. Add `tools/local_tables.py` with `create` and `delete` commands, and `make local-tables` / `make local-tables-delete` targets. The script is idempotent, waits until the table is active, and refuses any table name that does not start with `asternavium-local-`, so it cannot touch other tables in the account.
3. Add a moto fixture in `tests/conftest.py` that creates the same table from the same definition.
4. Run `AWS_PROFILE=savar make local-tables` once against the personal account.

**Done when:** `asternavium-local-app` exists in `eu-central-1` in the personal account, and tests create an identical table in moto.

### Step 4. Dev identity

1. Add a `Principal` value type (user ID only, for now) and a `get_current_user` dependency in `api/deps.py`.
2. When the environment is `dev`, read the user ID from the `X-Dev-User` header: required, 1 to 64 characters of letters, digits, `-` and `_`, otherwise `401` with code `unauthenticated`. In any other environment, always `401`.
3. Declare the header as an API key security scheme, so Swagger UI's Authorize dialog sets it for every request.
4. Tests: valid header, missing header, malformed header, and rejection outside `dev`.

**Done when:** Swagger UI shows the Authorize button and the dependency rejects the header outside `dev`.

### Step 5. Places dataset and search

1. Add `tools/geonames_snapshot.py`. It downloads `cities500.zip`, `admin1CodesASCII.txt` and `countryInfo.txt` from the GeoNames export, keeps only the columns the app needs (place ID, name, ASCII name, alternate names, region, country, latitude, longitude, population, time zone), and writes a compressed snapshot to `src/app/data/places/` together with its download date as the dataset version. The snapshot is committed, so builds are reproducible and the app never downloads data at runtime.
2. Check the snapshot size: the target is at most about 15 MB. If it is larger, drop rarely useful alternate names or switch to the `cities1000` list, and record the choice. Result: 11.7 MB for 226,134 places with all alternate names, so `cities500` stays. City districts (GeoNames `PPLX`, about 10,800 entries) are dropped, so searches are not crowded by them; the decision is to be confirmed before launch (specification, section 13).
3. A `PlaceRepository` Protocol (`search`, `get`, and the dataset version that step 7 stores with a profile) and a GeoNames implementation that loads the snapshot once into an in-memory index. Names, ASCII names and alternate names are normalised (case-folded, accents removed), so "Kyiv", "kyiv" and "Київ" all match. Search is a prefix match ranked by population, with places matching by their main or ASCII name ranked above places matching only by an alternate name: alternate names include nicknames such as "Paris of the North" for Warsaw, which would otherwise outrank real matches. It is CPU-bound and synchronous, as CLAUDE.md requires for pure in-memory work. Loading takes about 3 seconds and 150 MB at startup.
4. Router `api/v1/places.py` for `GET /v1/places`, behind the dev identity like every other endpoint, with input limits on the query and the result count.
5. Add the GeoNames attribution (CC-BY 4.0) to `NOTICE` and the README.
6. Tests: unit tests on a tiny synthetic dataset (prefix match, accent and case folding, ranking, an unknown place ID); a few smoke tests on the real snapshot with well-known cities, such as a Cyrillic query and an ambiguous name returning several countries.

**Done when:** `GET /v1/places?query=par` returns Paris, France first, followed by other places called Paris, each with its time zone.

### Step 6. Birth data model

Pure code with no I/O, in its own module.

1. A frozen birth data value type and its Pydantic boundary schema, with `extra="forbid"`: date (from 1900-01-01 on), time (required, to the minute, without a UTC offset), place ID and the ambiguity choice. Coordinates and time zone are not input: they come from the place found in step 5.
2. A function that converts the local birth date and time to a timezone-aware UTC `datetime`, raising `InvalidBirthDataError` for nonexistent times and for ambiguous times without a choice (decision D8); a missing time is rejected by the schema (decision D9). A second pure function rejects a birth instant in the future; it takes the current instant as an argument, and the profile service in step 7 passes the clock. Error messages name the problem, never the submitted values.
3. Tests with explicit cases: a DST spring-forward gap, a fall-back overlap with both choices, a date before a zone's historical offset change, midnight, 29 February in a leap year, a place ID that does not exist, a place at a polar latitude, and birth data without a time, which is rejected. Add Hypothesis property tests: for any valid non-ambiguous input, converting back to the local zone reproduces the local date and time.

**Done when:** the tests pass, and no test fixture is a real person's birth data.

### Step 7. Repositories

1. Small repository Protocols with async methods, one per item type: `ProfileRepository`, `SessionRepository`, `MessageRepository`. Callers depend only on these. `MessageRepository` also has `add`, which Phase 2 needs and the tests use to create messages.
2. DynamoDB implementations behind them, running `boto3` calls in a worker thread with `anyio` (decision D6; a direct dependency, already installed through Starlette). They translate `ClientError` into domain errors at the adapter boundary: throttling, server and network errors become `storage_unavailable` (`503`), and other AWS errors stay unhandled, because they indicate a bug. They use conditional writes where an item must or must not exist (for example, rename only an existing session).
3. Key builders and the cursor codec in one module; the cursor is an opaque, URL-safe encoding of the last item's sort key and is validated on the way in (`invalid_cursor`, `400`). The partition key always comes from the caller, so a cursor cannot reach another user's or session's items.
4. Record types returned by the repositories as frozen dataclasses, kept with the repositories; they are not the API schemas.
5. Tests against moto: create, read, list order and pagination across pages, rename of a missing session, delete with messages, and a user whose items do not leak into another user's queries.

**Done when:** repository tests cover every method, with at least 90% coverage of the repositories package.

### Step 8. Services

1. `SessionService`: create, list, get one (raising `SessionNotFoundError` when the caller does not own it), rename, delete including all messages, and list messages after the ownership check.
2. `ProfileService`: get the profile (or none) and replace it; resolves the place ID through `PlaceRepository`, copies its name, coordinates and time zone into the profile, and computes the UTC birth instant through the birth data module.
3. `AccountService`: delete the profile, every session and every message of one user. It is idempotent, so a retry after a partial failure finishes the job.
4. Domain errors under `BaseAppError`, each with a code and status: `session_not_found` (`404`), `place_not_found` (`422`) and `invalid_birth_data` (`422`); `invalid_cursor` (`400`) and `storage_unavailable` (`503`) already come from step 7.
5. Unit tests with in-memory fakes of the repository Protocols.

**Done when:** service tests pass and no service imports `boto3`.

### Step 9. API routers and schemas

1. Request and response schemas in `schemas/`: sessions, messages, pages (items plus `next_cursor`) and profile. Responses never include internal keys (`PK`, `SK`).
2. Routers `api/v1/sessions.py`, `api/v1/profile.py` (`PUT`) and `api/v1/me.py` (`GET` and `DELETE`), with no business logic: validate, call the service, map the result. Wire the services through `Depends` from the composition root.
3. Input limits: title length, page size, place query length, and the existing request validation that never echoes input.
4. API tests with `TestClient` against moto: every endpoint, the cross-user `404` for each session endpoint (for `DELETE`, `204` with the other user's session left intact), pagination, account deletion, and the `401` cases.

**Done when:** the API tests pass, and the OpenAPI schema in Swagger UI shows every endpoint with its error responses.

### Step 10. Local run and documentation

1. Run the app with `AWS_PROFILE=savar` and exercise the exit criteria in section 1 through Swagger UI with two test users.
2. Update the README: local setup (`.env`, `AWS_PROFILE`, `make local-tables`), the dev identity, how to reset local data, and how to refresh the GeoNames snapshot.
3. Update `.env.example` with the new settings.

**Done when:** a fresh clone can follow the README to a working local API with persistent sessions.

### Step 11. Phase close

1. Run `make check` and the manual Swagger UI walkthrough from section 1.
2. Record any decision changed during the phase in the specification.

## 7. Order and effort

Rough effort for one developer.

| Step | Depends on | Effort |
| --- | --- | --- |
| 1. Decisions and specification | – | 0.5 day |
| 2. Dependencies and settings | 1 | 0.5 day |
| 3. Table definition and script | 2 | 0.5 day |
| 4. Dev identity | 2 | 0.5 day |
| 5. Places dataset and search | 2, 4 | 1.5 days |
| 6. Birth data model | 5 | 1 day |
| 7. Repositories | 3 | 1.5 days |
| 8. Services | 6, 7 | 1 day |
| 9. API routers and schemas | 4, 8 | 1 day |
| 10. Local run and documentation | 9 | 0.5 day |
| 11. Phase close | all | 0.5 day |

Total: about 9 working days.

## 8. Risks

| Risk | Mitigation |
| --- | --- |
| A test or tool accidentally writes to the personal AWS account | Tests run inside moto's mock, which blocks real AWS calls; the table script only accepts `asternavium-local-*` names |
| Birth data leaks into logs or error responses | Validation errors never echo input (Phase 0); domain error messages contain no values; a test asserts that responses and log output from a profile update contain none of the submitted birth data |
| Sync `boto3` calls block the event loop | Every repository call runs in a worker thread; a review check that no `async` function calls `boto3` directly |
| Table definition drifts from the Terraform `data` module in Phase 4 | One table definition in the app; Phase 4, step 7 checks Terraform against it |
| Account deletion stops halfway (many messages, throttling) | Batched deletes with retries of unprocessed items; the operation is idempotent, so a repeat finishes it |
| A user's birth place is missing from the dataset | The `cities500` list covers only places with a known population of 500 or more, so most villages without a population figure are missing (in Ukraine, about 5,400 of 33,700 populated places are included). Accepted for the MVP: the user picks the nearest town, which shifts coordinates by a few kilometres and keeps the right time zone. A managed geocoding service is to be reconsidered before launch (specification, section 13) |
| The places snapshot bloats the repository | Only the needed columns, compressed; measured in step 5 at 11.7 MB for 226,134 places, so the `cities1000` fallback is not needed |
| Time zone handling picks a wrong offset for historical dates | Explicit test cases for historical offset changes and DST transitions; `zoneinfo` with the pinned `tzdata` package |

## 9. Out of scope for Phase 1

- `POST /v1/chat`, the agent, the LLM and the checkpoints table (Phase 2)
- Subscription and quota repositories, the Stripe customer GSI (Phase 6, decisions D4 and D5)
- Plan, entitlements and quota fields in `GET /v1/me` (Phases 5 and 6)
- Cognito and real authentication (Phase 5)
- Any Terraform, Docker image or deployment (Phase 4)
- Street addresses, villages below 500 inhabitants and online geocoding services
