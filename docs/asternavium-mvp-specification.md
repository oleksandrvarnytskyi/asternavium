# AsterNavium MVP: Specification and Step-by-Step Implementation

Oct 22, 2026

The MVP delivers an authenticated AI chat on top of one module, Jyotisha (Vedic astrology, with calculation tools), running serverless on AWS. It is free to use, with a limit of 8 chat requests per day and 30 per month per user. Bukvitsa for Slavic symbolic traditions (curated, source-based knowledge) and paid plans come after the MVP; Western astrology and numerology remain the next modules, then other traditions, learning paths and comparative reports.

## 1. MVP scope

### In scope

- FastAPI project with a clean, layered structure
- Two core endpoints: `POST` chat (assistant ↔ user) and `GET` bubble prompts (starter questions), plus the supporting endpoints listed in section 5
- User authentication (OAuth2 + JWT) and authorization (roles, ownership, usage limits)
- Multiple chat sessions per user
- Short-term memory (working context of an active session)
- Long-term memory (full chat history and profile in DynamoDB)
- Email notifications, at most 30 per user per month
- Free use with request limits: 8 chat requests per day and 30 per month per user
- Infrastructure as code in a separate Terraform repo, CI/CD pipelines, Datadog monitoring

### MVP modules

| Module | Nature | MVP content (confirm exact scope) |
| --- | --- | --- |
| Jyotisha | Calculation + interpretation | Sidereal birth chart, nakshatras, planetary periods (dasha), interpretation by documented classical rules |

After the MVP: Bukvitsa (Slavic symbolic traditions) as a separate knowledge service (section 3), then Western astrology and numerology, then further traditions.

### Out of scope (post-MVP)

- The Bukvitsa module and service (Slavic symbolic traditions; design kept in section 3)
- Paid plans, subscriptions and payments (Stripe or Paddle); the MVP is free with request limits (section 9)
- Push notifications; the MVP sends email only (section 8)
- Western astrology and numerology modules (the next modules after the MVP), then other traditions
- Learning paths, quizzes, comparative reports across traditions
- Retrieval over a knowledge base (RAG, vector search); MVP reads curated, versioned knowledge files through lookup tools instead
- Native mobile apps and the production web frontend (React with assistant-ui is parked until after the MVP; the MVP is API-first and uses Swagger UI and a Gradio test client)
- PDF reports, admin UI, referral or credit-pack pricing

### Assumptions to confirm

- Until the production web client exists, the API is exercised through Swagger UI (from Phase 1) and a Gradio test client (from Phase 2).
- Launch language is English; the assistant can answer in the user's language, but the glossary and prompts are English-only.
- Team of one backend developer; the production web client needs extra capacity.

### Success criteria

- A new user can sign up, ask a question and get an answer that clearly separates calculated results, traditional interpretation and AI explanation.
- Conversations persist and resume across sessions and devices.
- The request limits (8 per day, 30 per month) are enforced on every chat request; a user who reaches one gets `429` with the time the limit resets.
- p95 chat latency under 10 seconds (non-streaming), error rate under 1%.
- The whole environment can be rebuilt from the Terraform repo and the app pipeline with no manual steps.

## 2. Technology stack

Your proposed stack holds up. The main additions are Amazon Cognito for OAuth2/JWT, SQS plus EventBridge for notifications, and LangGraph (not just LangChain) for the agent and its short-term memory.

| Area | Choice | Notes |
| --- | --- | --- |
| Language, packaging | Python 3.13, `uv` | One `pyproject.toml` and `uv.lock`; `uv` also builds the Lambda image |
| API framework | FastAPI, Pydantic v2, pydantic-settings | Typed schemas, OpenAPI docs, settings from env |
| AI orchestration | LangChain + LangGraph | LangChain for models, prompts, tools; LangGraph for the agent graph, state and checkpointing |
| LLM provider | Amazon Bedrock, swappable via LangChain | IAM auth, no API keys, data stays in AWS. Direct Anthropic/OpenAI API is the alternative |
| LLM observability | LangSmith | Traces, prompt versions, datasets and evals |
| Compute | AWS Lambda (container image, `arm64`) + Lambda Web Adapter | FastAPI runs unchanged; image avoids the zip size limit that LangChain dependencies hit; Graviton (`arm64`) costs less per GB-second than `x86_64` |
| Region | `eu-central-1` (Frankfurt) | Both AWS accounts; check Bedrock model availability there before Phase 2 |
| API entry | API Gateway (REST API) | Supports response streaming since Nov 2025, so SSE chat is possible later |
| Authentication | Amazon Cognito user pool | OAuth2 authorization code + PKCE, social login, JWT access tokens |
| Database | DynamoDB, on-demand | Single-table design for app data; separate table for LangGraph checkpoints |
| Email | Amazon SES | Transactional and digest emails, at most 30 per user per month |
| Async, scheduling | SQS, EventBridge Scheduler, Lambda workers | Notification fan-out, retries, dead-letter queue |
| Secrets, config | Secrets Manager, SSM Parameter Store | LangSmith key; non-secret config |
| IaC | Terraform in a separate repo | S3 remote state with native locking; modules + `dev`/`prod` environments |
| CI/CD | GitHub Actions with AWS OIDC (assumed) | No long-lived AWS keys. CodePipeline is the alternative |
| Monitoring | Datadog, EU site (`datadoghq.eu`) | Lambda extension, `ddtrace`, JSON logs; monitors and dashboards via the Datadog Terraform provider. Set up in Phase 5, after authentication; until then, local console logs (Phases 1 and 2), then CloudWatch Logs and the built-in Lambda and API Gateway metrics |
| Quality | pytest, anyio, httpx, moto, ruff, mypy, pre-commit | Fake chat models for deterministic LLM tests |

**Web clients:** FastAPI's built-in Swagger UI from Phase 1 (Cognito sign-in from Phase 4), a Gradio test client from Phase 2 (local, then `dev` only from Phase 3), and React with assistant-ui for the production release after the MVP.

### Key decisions

- **Cognito instead of a hand-built OAuth2 server.** It already issues and rotates JWTs, handles social login, password reset and MFA. FastAPI only validates tokens via the JWKS endpoint. Building your own OAuth2 provider is the main security risk to avoid in an MVP.
- **LangGraph over plain LangChain chains.** You need stateful sessions, tool calls to calculation engines, and resumable threads. LangGraph checkpoints give per-session short-term memory out of the box.
- **Lambda container image.** LangChain, boto3 and an ephemeris library easily exceed 250 MB unzipped. Add provisioned concurrency only if cold starts hurt.
- **DynamoDB through `boto3` in a worker thread.** Repository methods are `async` and run their synchronous `boto3` calls with `anyio.to_thread`, so the event loop never blocks. `aioboto3` was not chosen: moto's in-process mock and `langgraph-checkpoint-aws` are built on `boto3`, and the checkpointer uses the same thread pattern.
- **DynamoDB for both memories.** AWS documents a `DynamoDBSaver` in `langgraph-checkpoint-aws` with TTL, compression and optional S3 offload for large checkpoints; no Redis or VPC is needed in the MVP.
- **Jyotisha engine: `jyotishganit`.** Charts come from [`jyotishganit`](https://github.com/northtara/jyotishganit) (MIT), which computes positions with Skyfield (MIT) and NASA JPL's DE421 ephemeris (public domain) and adds nakshatras, whole sign houses and Vimshottari dashas. It runs locally, so birth data never leaves the system. It replaces Swiss Ephemeris, whose free licence is the AGPL. The library is young (beta), so it is wrapped behind the engine's own interface, pinned to an exact version and checked by golden tests, and its data files are bundled instead of downloaded at runtime; if it falls short, the adapter can be replaced by an own engine on Skyfield. Its conventions are the module assumptions: True Chitra Paksha ayanamsa, whole sign houses, mean lunar nodes, Vimshottari dasha with a sidereal year of 365.25636 days. VedAstro.Python was rejected because it sends birth data to its own cloud API.
- **Proprietary licence.** With no copyleft dependency left, the application is proprietary (all rights reserved) instead of the AGPL-3.0; section 14 lists what this changes.

## 3. Architecture

*Diagram (see the live document):* the web client calls API Gateway (WAF, rate limits), which invokes one FastAPI Lambda containing the LangGraph agent and the Jyotisha engine. The Lambda uses Amazon Cognito (login, JWT), DynamoDB (history, memory and usage counters) and Amazon Bedrock (LLM). A separate asynchronous notification path runs EventBridge Scheduler → SQS + DLQ → Worker Lambda → Amazon SES (email). Datadog and LangSmith observe every function.

A chat request enters through API Gateway, is authenticated with a Cognito JWT, and runs the LangGraph agent inside one FastAPI Lambda, which reads and writes DynamoDB and calls the LLM. Notifications run on a separate asynchronous path.

There are two repositories: `asternavium` (application code and the image pipeline) and `asternavium-infra` (Terraform). After the MVP, a third, `asternavium-bukvitsa`, will hold the Bukvitsa knowledge service. Terraform owns the infrastructure; the application pipelines only ship new images.

### Bukvitsa service (after the MVP)

Moved after the MVP; the design is kept so the work can start without rework. The `bukvitsa` value stays in the code's module and tradition enums, and chat refuses it with `422 module_unavailable` until the module exists.

The Bukvitsa module, covering the Slavic symbolic traditions, is a separate service, so its content, release cycle and licence do not depend on the main application. It is knowledge-first: the traditions it covers are unevenly documented and often reconstructed, so it serves curated, sourced entries with their reliability noted, and the agent must not invent calculation rules.

- **Interface:** a small read-only HTTPS API over curated entries (search by keyword or topic, get one entry by ID). Each entry returns its text, language, sources and a note on how reliable the source is, so the agent can cite it and separate source-based statements from interpretation.
- **Calling it:** the main API has a `bukvitsa_client` in `integrations/` and exposes it to the agent as a tool. Calls use IAM authentication or a service key, with a short timeout; if the service is down, the agent says the Bukvitsa content is unavailable instead of inventing an answer.
- **Hosting:** the same pattern as the main API: Lambda container image with its own pipeline and Terraform module in the infra repo, in `dev` first (`prod` follows in Phase 7). Start with versioned, validated content files bundled with the service; move to a database or retrieval later if the library outgrows that.
- **Content quality:** a schema check in CI rejects entries without a source; the content version is returned with every response.
- **Licensing:** its content and licence are decided with the module (section 14).

## 4. FastAPI project structure

The app repo (`asternavium`) uses a `src/` layout with strict layering: routers call services, services call repositories, agents and integrations, and the calculation engines in `domain/` stay pure Python with no AWS or LLM imports. That separation is what lets new traditions be added as modules later.

```
asternavium/
├── pyproject.toml            # uv-managed, ruff + mypy + pytest config
├── uv.lock
├── Dockerfile                # Lambda container image + Lambda Web Adapter
├── LICENSE                   # proprietary licence, all rights reserved
├── NOTICE                    # third-party licence notices and data attributions
├── Makefile                  # lint, test, run, build, deploy shortcuts
├── .pre-commit-config.yaml
├── .github/workflows/        # ci.yml (PR), deploy.yml (main)
├── src/app/
│   ├── main.py               # create_app() factory, middleware, error handlers
│   ├── core/                 # config.py (pydantic-settings), logging.py, errors.py, security.py
│   ├── api/
│   │   ├── deps.py           # current_user, service providers
│   │   └── v1/               # router.py, chat.py, prompts.py, sessions.py, persons.py,
│   │                         # profile.py, places.py, me.py, notifications.py, about.py
│   ├── schemas/              # Pydantic request/response models
│   ├── services/             # chat, sessions, persons, profiles, accounts, quota, notifications
│   ├── agents/               # LangGraph graph, prompts, tools, memory (checkpointer)
│   ├── domain/               # modules: jyotisha/ (engine); later western/, numerology/
│   ├── repositories/         # DynamoDB access: profiles, persons, sessions, messages, quota, notification prefs
│   ├── integrations/         # llm_factory, tracing, ses_client
│   ├── workers/              # Lambda handlers: notification_worker, scheduler
│   └── data/                 # bubble_prompts.json, glossary/ (versioned content)
└── tests/
    ├── unit/                 # domain engines, services, prompt builders
    ├── api/                  # TestClient + dependency overrides
    ├── integration/          # moto / DynamoDB Local
    └── conftest.py
```

### Conventions

- App factory plus `pydantic-settings`; every setting comes from env vars, secrets from Secrets Manager at cold start.
- API versioned under `/v1`; one router per resource; no business logic in routers.
- Dependency injection through `Depends` so tests can swap repositories, the LLM and SES for fakes.
- One error model (`{code, message, request_id}`) and a global exception handler; no stack traces to clients.
- Request ID middleware; structured JSON logging that carries `request_id`, `session_id`, hashed `user_id` and, from Phase 5, the Datadog trace ID.
- Lambda functions share one image: the API function and the workers differ only by command or handler.

## 5. API design

The two endpoints you named stay the core. Multiple sessions, persons and notifications need a few more routes, all small. Login itself is handled by Cognito's hosted UI (authorization code + PKCE), so the API has no login endpoint.

| Method, path | Auth | Purpose |
| --- | --- | --- |
| `GET /v1/prompts` | Public | Bubble prompts for the start screen. Query: `locale`, `module`. Static JSON, cacheable, so it is fast for anonymous visitors |
| `POST /v1/chat` | JWT + limits | Send a message. Body: `session_id` (optional, new session if omitted), `message`, `module`, `person_id` (for a new Jyotisha session: the person whose chart it is about, from `GET /v1/persons`; defaults to the user's own person; stored on the session and fixed for its lifetime), `locale`, `answer_depth` (optional, `simple`, `detailed` or `technical`; overrides the profile's default for this answer, which falls back to `simple` without a profile). Returns `session_id`, `message_id`, `reply`, `references`, `usage` and remaining quota |
| `GET /v1/me` | JWT | User ID and profile (from Phase 1; `profile` is `null` until the first `PUT /v1/profile`); the remaining requests of the day and the month are added in Phase 5 |
| `DELETE /v1/me` | JWT | Delete the account and all its data (profile, persons, sessions, messages); idempotent |
| `PUT /v1/profile` | JWT | Traditions the user is interested in (one or more, unordered), language, answer depth (default depth of answers) and, optionally, which of the user's persons is the user (`owner_person_id`) |
| `GET` / `POST /v1/persons` | JWT | List or add the people the user makes charts for (the user, relatives, clients): a label and birth data (date, time to the minute, place ID from `GET /v1/places`); paginated |
| `GET` / `PUT` / `DELETE /v1/persons/{id}` | JWT | Read, replace or delete one person; deleting is idempotent |
| `GET /v1/places` | JWT | Search birthplaces by name in a GeoNames city dataset bundled with the app; returns place ID, name, region, country and time zone. The server fills in coordinates and time zone from the chosen place, so no birth place is sent to an external service |
| `GET /v1/sessions` | JWT | List sessions (title, module, last activity), paginated |
| `GET /v1/sessions/{id}/messages` | JWT | Paginated history of one session |
| `PATCH` / `DELETE /v1/sessions/{id}` | JWT | Rename or delete a session (with its messages); deleting is idempotent |
| `PUT /v1/notifications/preferences` | JWT | Email opt-ins by type |
| `GET /health` | Public | Liveness for monitors |

### Conventions of the resource endpoints

Settled in Phase 1 and shared by sessions, messages, persons and the profile:

- **Pagination.** Lists are newest first with an opaque `cursor`; the response holds `items` and `next_cursor` (`null` on the last page). `limit` defaults to 20, at most 50. A cursor the API did not issue for that list returns `400 invalid_cursor`.
- **Ownership.** Another user's session or person is reported exactly like a missing one: `404 session_not_found` or `404 person_not_found`. A delete returns `204` either way and changes nothing for an ID the caller does not own, since a repeated delete by the owner cannot be told apart from another user's ID.
- **IDs.** Session and person IDs are ULIDs issued by the API; a malformed ID returns `422` before any database call.
- **Input limits.** Session title 1 to 100 characters and person label 1 to 50 characters, both after trimming; place search query 2 to 100 characters. Validation errors list field locations and reasons, never the submitted values.
- **Birth data.** Date and local time to the minute, as ISO text (a number is rejected), plus a place ID from `GET /v1/places` (`422 place_not_found` otherwise). A local time skipped by a clock change is rejected; a time that occurred twice needs `ambiguous_time` (`earlier` or `later`); either problem, or a birth in the future, returns `422 invalid_birth_data`. Responses return the time as `HH:MM`, the saved place without coordinates, and the UTC instant.
- **Profile.** `PUT /v1/profile` replaces the whole profile; omitted fields take their defaults (`en`, `[jyotisha]`, `simple`, no owner person). Traditions must not repeat. `GET /v1/me` reports an `owner_person_id` whose person no longer exists as `null`.
- **Errors.** Every error uses the shared model; `503 storage_unavailable` means the database failed after retries and the request may be repeated.

### Chat contract details

- **Request validation.** Message length cap (for example 2,000 characters); `module` is an enum (`jyotisha`, `general`; `bukvitsa` stays in the enum but is refused with `422 module_unavailable` until the module exists after the MVP).
- **Response labels.** Each answer carries structured parts: `calculated` (engine output), `traditional` (source-based statements), `interpretation` (AI explanation). This implements the platform's transparency principle and lets the client style them differently.
- **Idempotency.** Optional `Idempotency-Key` header so a retried request is not counted against the limits twice.
- **Streaming (after the MVP).** `POST /v1/chat/stream` over SSE using the same service, enabled by API Gateway response streaming and Lambda Web Adapter.
- **Errors.** `401` unauthenticated, `429 limit_reached` (daily or monthly, with the reset time), `422` validation.

## 6. Authentication and authorization

Cognito authenticates; the API authorizes. Tokens prove who the user is, while the usage counters live in DynamoDB.

### Authentication flow

1. The client sends the user to the Cognito hosted UI (authorization code + PKCE); email/password plus Google and Apple sign-in.
2. Cognito returns an access token (JWT, about 1 hour) and a refresh token.
3. The client calls the API with `Authorization: Bearer <access_token>`.
4. FastAPI validates signature (cached JWKS), issuer, audience/client ID, expiry and `token_use=access`, then loads the user from `sub`.
5. A Cognito post-confirmation trigger (Lambda) enqueues the welcome email; the profile is created by the first `PUT /v1/profile`.

If you prefer to own the OAuth2 flow in FastAPI (`OAuth2PasswordBearer` plus self-issued JWTs), it is feasible, but you then also build registration, password reset, email verification, refresh rotation and brute-force protection. That is a poor trade for an MVP.

### Authorization model

| Layer | Mechanism | Example |
| --- | --- | --- |
| Identity | JWT `sub`, Cognito groups | `admin` group for internal endpoints |
| Resource ownership | Check `USER#<sub>` owns the session or person on every session, message or person call | A user cannot read another user's session or person |
| Usage limits | Atomic counters in DynamoDB per user per day and per month; limits from settings, the same for every user | Chat request 9 of a day, or 31 of a month, returns `429` |

Implementation: the FastAPI dependency `get_current_user()` and a limit check in the chat service; services never trust client-supplied user IDs. Add an API Gateway usage plan or WAF rate rule per IP as a first line of defense against abuse.

## 7. Sessions and memory

Lambda is stateless, so both memories live in DynamoDB. A session is one conversation thread; its `session_id` doubles as the LangGraph `thread_id`.

|  | Short-term memory | Long-term memory |
| --- | --- | --- |
| Purpose | Working context of the active session | Permanent chat history and user profile |
| Store | LangGraph `DynamoDBSaver` table (checkpoints) | App table: `SESSION` and `MSG` items |
| Lifetime | TTL, for example 7 days after last activity | Until the user deletes it or the account |
| Content | Graph state, last N messages, rolling summary | Every message with role, text, tokens, model, trace ID |
| Read by | The agent on every turn | Sessions list, history screen, notification content |

### Chat turn, step by step

1. Validate the JWT and load the user.
2. Check and increment the daily and monthly counters atomically (one conditional transaction over both items).
3. Load or create the session; verify the user owns it.
4. Run the LangGraph agent with `thread_id = session_id`; the checkpointer restores short-term state.
5. Trim context to a token budget: system prompt, profile facts, rolling summary, last N messages.
6. The agent may call tools (Jyotisha engine, glossary) and then composes the answer.
7. Persist the user message and the answer to long-term storage; update session title and `updated_at`.
8. Return the response with the remaining requests; give the request back on both counters if the LLM call fails.

### DynamoDB single-table design (app table)

| Item | PK | SK | Key attributes |
| --- | --- | --- | --- |
| Profile | `USER#<id>` | `PROFILE` | email, locale, traditions (string set), answer depth, owner person ID (the person who is the account owner) |
| Person | `USER#<id>` | `PERSON#<ulid>` | label, birth data (local date and time, place copied from the dataset, UTC instant), created, updated |
| Session | `USER#<id>` | `SESSION#<ulid>` | title, module, person ID (Jyotisha sessions, from Phase 2), created, updated, message count |
| Message | `SESSION#<id>` | `MSG#<ulid>` | role, content, tokens in/out, model, trace ID |
| Daily usage | `USER#<id>` | `USAGE#DAY#<yyyy-mm-dd>` | chat request count, TTL |
| Monthly usage | `USER#<id>` | `USAGE#MONTH#<yyyy-mm>` | chat request count, email count, TTL |
| Notification prefs | `USER#<id>` | `NOTIFPREFS` | email opt-ins |

The app table is named `asternavium-<environment>-app`: `asternavium-local-app` for local development, `asternavium-dev-app` and `asternavium-prod-app` in the AWS environments; the name reaches the app through the `ASTERNAVIUM_APP_TABLE_NAME` setting. ULIDs keep sessions and messages time-ordered, so listing newest first is a plain `Query`. Enable on-demand capacity, point-in-time recovery and KMS encryption. Account deletion removes every `USER#<id>` item and the user's sessions' messages (needed for GDPR).

## 8. Notifications (email)

Notifications are email only in the MVP and never block a chat request: producers put a message on SQS, a worker Lambda checks the user's preferences and monthly email count, then sends through SES. Push notifications come after the MVP.

| Notification | Default |
| --- | --- |
| Welcome | Always (transactional) |
| Weekly digest (cycles and highlights from the chart of the user's own person) | Opt-in |
| Significant transit or cycle alert | Opt-in |

**Monthly cap:** at most 30 emails per user per calendar month (UTC), counted on the user's monthly usage item before each send; a send over the cap is dropped and logged by count only. Cognito's own verification and password-reset emails are not sent by the worker and do not count.

### Components

- **EventBridge Scheduler** fires per-user or hourly batch triggers (respecting the user's time zone) that enqueue notification jobs.
- **SQS queue + dead-letter queue** gives retries and visibility into failures.
- **Worker Lambda** loads the user, checks the opt-in and the monthly cap, renders the template, sends, and records the result.
- **SES** with a verified domain, DKIM, SPF, DMARC; bounce and complaint events (SNS) suppress future sends.
- Every email carries an unsubscribe link, which updates `NOTIFPREFS`.

SES starts in sandbox mode; request production access at the start of Phase 7, since approval can take a few days.

## 9. Usage limits and cost control

The MVP is free for every user, with the same limits for everyone. All values come from settings, so they can be tuned after the first users arrive without a code change.

| Limit | Value |
| --- | --- |
| Chat requests (`POST /v1/chat`, any module) | 8 per day and 30 per month per user |
| Emails | 30 per month per user (section 8) |
| Persons with birth charts | A fixed number per user from settings (proposal: 10, to confirm in Phase 5) |
| Sessions and history | No separate limit in the MVP; history is kept until the user deletes it |

- **Counting.** A day and a month are UTC calendar periods: the daily limit resets at 00:00 UTC, the monthly one on the first of the month at 00:00 UTC. Each chat request increments both counters in one conditional transaction, so request 9 of a day or 31 of a month is rejected before the agent runs; a request is given back on both counters if the LLM call fails.
- **Response.** `429 limit_reached` names the limit (`daily` or `monthly`) and its reset time; `GET /v1/me` and every chat response report the remaining requests of the day and the month.
- **Cost control.** Log tokens and estimated cost per request in the message item and as a Datadog metric, so the cost per user is visible from day one; cap input length, output tokens and tool-call loops per request; an AWS budget alert per account.
- **After the MVP.** Paid plans (Stripe, or Paddle as merchant of record) would turn these values into per-plan limits; the counters and the `429` contract stay the same.

## 10. Infrastructure and CI/CD

Infrastructure lives in its own repo (`asternavium-infra`) so that cloud changes have their own review and approval path. The infra repo and the app repo (`asternavium`) meet through one contract: Terraform creates the Lambda functions and outputs their names; each service pipeline only pushes images and updates its own function code.

```
asternavium-infra/
├── bootstrap/            # state bucket, GitHub OIDC roles (applied once, per account)
├── modules/
│   ├── api/              # ECR, Lambda, API Gateway, WAF, custom domain + ACM
│   ├── auth/             # Cognito user pool, app client, hosted UI domain, triggers
│   ├── data/             # DynamoDB app table, checkpoints table, KMS, backups
│   ├── notifications/    # SQS + DLQ, EventBridge Scheduler, worker Lambda, SES identity
│   ├── secrets/          # Secrets Manager entries, SSM parameters
│   └── observability/    # Datadog AWS integration, monitors, dashboards
├── envs/
│   ├── dev/              # main.tf, variables, backend config
│   └── prod/
└── .github/workflows/    # plan on PR, apply on merge, manual approval for prod
```

### Principles

- Region `eu-central-1` (Frankfurt) for every resource in both accounts; Lambda functions run on `arm64`.
- Separate AWS accounts for `dev` and `prod` (AWS Organizations); one state file per environment in S3 with native lockfile locking and versioning.
- Lambda resources use `ignore_changes` on the image URI; the app pipeline deploys new image versions and moves a `live` alias, which allows instant rollback.
- Least-privilege IAM: the API role can reach only its tables, its secrets and the chosen Bedrock models.
- Secret values are never in Terraform state: Terraform creates the secret containers; values are set out-of-band.
- Pre-merge checks: `terraform fmt`, `validate`, `tflint`, a security scanner (Trivy or Checkov), and a `plan` posted to the pull request.

### Application pipeline (`asternavium`)

1. **Pull request:** ruff, mypy, pytest with coverage gate, dependency audit, Docker build.
2. **Merge to main:** build image, push to ECR (tagged by commit SHA), deploy to `dev`, run smoke tests.
3. **Release tag:** promote the same image to `prod` after manual approval, shift the alias gradually, auto-rollback on alarm.

GitHub Actions authenticates to AWS with OIDC roles from `bootstrap/`; no stored AWS keys.

### Environments (dev and prod)

The same image is promoted from `dev` to `prod`; only variables and secrets differ. All prod setup is done in the last phase (Phase 7), after the whole MVP is implemented and tested in dev. Terraform state and secrets are separate per environment. In the infra repo, pull requests run `plan` for both environments, and a merge applies `dev` automatically while `prod` waits for approval of the reviewed plan.

| Aspect | dev | prod |
| --- | --- | --- |
| AWS account | Own account | Own account |
| App deploy | Automatic on every merge to `main` | Release tag, manual approval, gradual alias shift |
| Cognito | Own user pool, test users | Own user pool, real users |
| LLM, limits | Cheaper model, low limits | Production model and limits |
| SES | Sandbox with verified addresses | Production access |
| Datadog, LangSmith | `env:dev` tag, separate LangSmith project | `env:prod` tag, separate project, content hidden |
| Swagger UI (`/docs`) | Enabled; dev identity until Phase 4, then Cognito sign-in | Disabled |
| Gradio test client | Enabled (dev only); Lambda first, Fargate as fallback | Not deployed by default; Fargate (0.25 vCPU, 1 GB) if it is ever needed |
| Data | Disposable | Point-in-time recovery, deletion protection |

## 11. Observability and testing

### Datadog and LangSmith

Datadog (EU site, `datadoghq.eu`) is set up in Phase 5, after authentication. Until then, the app's JSON logs, which already carry request IDs, go to the console while Phases 1 and 2 run locally, and to CloudWatch Logs from Phase 3, together with the built-in Lambda and API Gateway metrics.

- **Datadog:** the Lambda extension and `ddtrace` provide APM traces across API Gateway, Lambda, DynamoDB and outbound calls; logs are structured JSON with a shared request and trace ID.
- **Custom metrics:** `llm.tokens.input/output`, `llm.latency`, `llm.cost_estimate`, `limits.reached` (by `daily` or `monthly`), `notifications.sent/failed/capped`, `signups`.
- **Monitors (as code):** 5xx rate, p95 latency, LLM error rate, DLQ depth above zero, Lambda throttles, DynamoDB throttles, daily cost anomaly.
- **LangSmith:** traces every agent run (prompts, tool calls, token use), holds prompt versions and an evaluation dataset of golden questions. Tag runs with `env`, `module` and the prompt version.
- **Privacy:** never log message text or birth data to Datadog. For LangSmith, enable input/output hiding or anonymization in `prod` unless the privacy policy and user consent cover storing conversations there.

### Testing strategy

| Layer | Approach |
| --- | --- |
| Calculation engines | Pure unit tests with golden cases (known Jyotisha charts checked against a reference chart tool) |
| Services and repositories | pytest with `moto` or DynamoDB Local; table creation fixtures |
| API | `TestClient`/`httpx` with dependency overrides for auth, LLM and SES |
| Agent | LangChain fake chat models for deterministic graph tests; assert tool selection and response structure |
| Prompt quality | LangSmith evals on a golden dataset; non-blocking in CI at first, a gate later |
| Usage limits | Boundary tests: request 8 and 9 of a day, 30 and 31 of a month, UTC day and month rollover, concurrent requests, the give-back on a failed LLM call |
| Infrastructure | `validate`, lint, scan, plan; post-deploy smoke test against `dev` |

Aim for 80% coverage on `services/` and `domain/`; do not chase coverage on glue code.

## 12. Step-by-step implementation

Eight phases. Phases 1 and 2 build the core functionality (data layer and sessions, then chat with the Jyotisha engine) and run it locally; Phase 3 sets up AWS and deploys everything built so far to `dev`; from then on, every phase ends with something deployed and testable in `dev`. After the foundation come authentication, observability and usage limits, email notifications, then hardening. The Bukvitsa service and paid plans come after the MVP (section 1). The phases assume one backend developer working mostly in sequence.

**Local development until Phase 3.** The app runs on the developer's machine against a personal AWS account, accessed with an access-key profile, in `eu-central-1`. That account is used only for Amazon Bedrock and for on-demand DynamoDB tables named `asternavium-local-*`, which a script in the app repository creates with the same keys, indexes and TTL as the Terraform `data` module will. Tests never call AWS: they use moto, and LLM tests use fake chat models. Phase 3 replaces this setup with AWS Organizations, IAM Identity Center and Terraform, following best practices, and retires the personal account from the project.

### Phase 0. Decisions and setup

1. Confirm the open decisions in section 13 (Stripe legal entity, Jyotisha settings, Bukvitsa source scope, CI system), and start curating Bukvitsa sources, which continues in parallel (the module itself moved after the MVP). Also decide what is published: the application repository goes public under the AGPL-3.0 (section 14), so the Terraform repo and the Bukvitsa service need an explicit decision on what is public and under which licence.
2. Create the repos, branch protection and PR templates.
3. `uv init`, ruff, mypy, pytest, pre-commit; Makefile with `lint`, `test`, `run`.
4. App skeleton: app factory, settings, JSON logging, error model, request ID middleware, `GET /health`, and `GET /v1/about` as the source link, with the AGPL-3.0 licence file and notices (section 14).

**Done when:** `make test` passes in CI.

### Phase 1. Data layer and sessions (local)

1. Local tables: a script creates the `asternavium-local-app` table (keys and TTL as in section 7) in the personal AWS account; table names come from settings, so Phase 3 only changes configuration.
2. Repositories for profile, person, session and message; moto-based tests. The usage counters move to Phase 5, where they are first used.
3. Session endpoints (list, history, rename, delete) with ownership checks; `GET /v1/me`, `PUT /v1/profile` and `DELETE /v1/me` (account deletion); persons endpoints for the birth data of the user and of other people; `GET /v1/places` for birthplaces.
4. Temporary `POST /v1/sessions` (module, optional title), so sessions can be created and the endpoints above tested before `POST /v1/chat` exists. It is removed in Phase 2.
5. Temporary dev identity: `get_current_user` reads a test user from an `X-Dev-User` header when the environment is `dev`, so sessions can be built and tested before Cognito exists. It is removed in Phase 4, and a test asserts it is disabled in `prod`.

**Done when:** sessions can be created and listed per test user, and cross-user access returns `404` (`204` for a delete, which changes nothing), so a session's existence is not revealed.

**Status:** done. The exit criteria were checked against the `asternavium-local-app` table with two test users, through HTTP calls and in Swagger UI. The detailed steps and decisions are in `phase-1-implementation-plan.md`.

**Web client from this phase:** Swagger UI (`/docs`), enabled in `dev` and disabled in `prod`. It uses the dev identity until Phase 4 adds the Cognito Authorize button.

### Phase 2. AI core: chat, prompts, memory (local)

1. LLM factory (`init_chat_model`) with Bedrock in the personal AWS account (model access enabled in `eu-central-1`); model and limits come from settings.
2. Jyotisha engine on `jyotishganit` (MIT; Skyfield and NASA JPL DE421 data) behind the engine's own interface: the library supplies positions, nakshatras, whole sign houses and Vimshottari dashas; its data files are bundled, and golden tests against a reference chart tool check the results.
3. LangGraph agent: system prompt that enforces the platform's transparency and disclaimer rules, tools for the Jyotisha engine and the glossary, `DynamoDBSaver` checkpointer on a local `asternavium-local-checkpoints` table (added to the table script), context trimming and summary. The Bukvitsa tool comes after the MVP.
4. `POST /v1/chat` using the chat turn sequence from section 7 (the usage limits arrive in Phase 5); `GET /v1/prompts` serving versioned bubble prompts. Remove the temporary `POST /v1/sessions` from Phase 1, so `POST /v1/chat` is the only way to create a session; tests that need a session create it through chat. A Jyotisha session stores the `person_id` it is about; deleting a person also deletes that person's sessions, because their history holds the person's chart.
5. LangSmith project, tracing, golden dataset (about 30 questions), first eval run.

**Done when:** a test user holds two parallel sessions, each remembers its own context, and history survives an app restart.

**Web client from this phase:** a Gradio test client in its own folder (`tools/gradio_client/`), run locally against the local API with the dev identity (a Cognito token from Phase 4). It is hosted in `dev` from Phase 3.

### Phase 3. Foundation and first deploy

1. AWS setup: an AWS Organization with the `dev` account, an IAM Identity Center admin user with MFA and an SSO CLI profile, and a budget alert. This replaces the personal account's access keys for project work.
2. Infra repo: `bootstrap/` (state bucket, OIDC roles), then `dev` with ECR, Lambda, API Gateway and WAF; the `data` module (app table, checkpoints table, TTL, PITR, KMS), which replaces the local table script; and secrets. The API role reaches only its tables, its secrets and the chosen Bedrock models.
3. Dockerfile with Lambda Web Adapter (`arm64` image, with the bundled ephemeris data files); pipeline builds, pushes and deploys the image.
4. CloudWatch log groups with JSON logs that carry request IDs. Datadog is set up later, in Phase 5.
5. Gradio test client hosted in `dev`: try Lambda first (container image, Function URL with response streaming, reserved concurrency of 1) as a one-day spike. If Gradio's streaming or session state misbehaves there, fall back to Fargate with 0.25 vCPU and 1 GB, roughly $10 a month if always on and less with a schedule that stops it outside working hours (rates from a May 2026 article; check current AWS pricing). App Runner is not an option because AWS closed it to new customers. Running Gradio locally against the `dev` API stays the free alternative.
6. Retire the personal AWS account from the project: delete the `asternavium-local-*` tables and stop using its keys in project configuration.

**Done when:** a commit to `main` deploys the API to `dev`; `/health`, sessions and chat with Bedrock work there; and JSON logs with request IDs appear in CloudWatch.

**Dev only until the end:** everything related to `prod` is done in Phase 7, after the whole MVP is implemented and tested in `dev`.

### Phase 4. Authentication and authorization

1. Terraform `auth` module: Cognito user pool for dev, app client, hosted UI, Google and Apple identity providers (the post-confirmation trigger for the welcome email follows in Phase 6; the prod pool is created in Phase 7).
2. JWT validation dependency with cached JWKS; `get_current_user`, group-based admin check.
3. `GET /v1/me` (in place since Phase 1) resolves the user from the token; tests with signed test tokens.
4. Replace the dev identity with Cognito and remove the `X-Dev-User` path. Wire Swagger UI's Authorize button to Cognito (authorization code + PKCE; register the Swagger redirect URL on the `dev` app client) and give the Gradio client a Cognito token.

**Done when:** a user signs up through the hosted UI, `GET /v1/me` returns their profile, and the dev identity no longer works anywhere.

### Phase 5. Observability and usage limits

1. Datadog on the EU site (`datadoghq.eu`): Lambda extension and `ddtrace` in the image, Datadog trace IDs in the JSON logs, a Terraform `observability` module with the Datadog provider and a first dashboard, and the custom metrics for tokens and estimated cost per request (section 9), so the cost per user is visible from the first users.
2. Usage limits (section 9): daily and monthly counters on the app table, checked and incremented in one conditional transaction before the agent runs, given back when the LLM call fails; `429 limit_reached` with the limit and its reset time; the remaining requests in `GET /v1/me` and in every chat response. The limit values and the number of persons per user come from settings.
3. The `Idempotency-Key` header on `POST /v1/chat`, so a retried request is answered once and counted once.
4. Tests on the boundaries: request 8 and 9 of a day, 30 and 31 of a month across several days, the UTC day and month rollover, concurrent requests from one user, and the give-back after a failed LLM call.

**Done when:** traces and cost-per-request metrics appear in Datadog, request 9 of a day and request 31 of a month return `429` with the reset time in `dev`, and a failed LLM call does not use up a request.

### Phase 6. Notifications

1. Terraform `notifications` module: SQS and DLQ, EventBridge Scheduler, worker Lambda, SES identity in sandbox mode (production access is requested in Phase 7).
2. Preferences endpoint and email templates.
3. Worker with the opt-in check, the monthly cap of 30 emails per user (section 8), bounce and unsubscribe handling; the welcome email and the weekly digest and alert jobs.

**Done when:** a test user receives the welcome email and an opted-in weekly digest, an opted-out user receives no digest, and email 31 of a month for one user is not sent.

### Phase 7. Hardening and launch

1. Datadog monitors and dashboards as code; alerting to the on-call channel; runbooks for DLQ and usage limit incidents.
2. Load test for the chat path; tune Lambda memory, timeouts and cold starts; decide on provisioned concurrency.
3. Security review: IAM, WAF rules, prompt-injection tests, secrets, dependency audit.
4. Privacy and legal: privacy policy, terms, astrology disclaimer, data deletion and export flow, LangSmith data handling, a check of the third-party notices and data attributions, and a real person or company named as the copyright holder in `LICENSE` and `NOTICE` instead of "AsterNavium contributors" (section 14).
5. Set up `prod`: create the `prod` AWS account (state, OIDC role), apply the `prod` Terraform environment (API, data, Cognito pool, notifications), create the release pipeline with manual approval and gradual alias shift, and configure the production services (SES production access requested at the start of this phase, Datadog and LangSmith `prod` settings). Promote the same image that passed testing in `dev` and run the smoke test.

**Done when:** the success criteria in section 1 are met in `prod`.

### After the MVP: next modules

1. The Bukvitsa service (design in section 3), with its own repository, Terraform module and pipeline, after its first curated content set is reviewed.
2. Paid plans with Stripe, or Paddle as merchant of record: the limits in section 9 become per-plan values; push notifications with Firebase Cloud Messaging.
3. Western astrology and Pythagorean numerology, each as its own `domain/` package and `module` value, reusing chat, memory, usage limits and notifications unchanged.
4. Then other traditions, learning paths and comparative analysis across modules.

Production web client, in parallel with the module work: React with assistant-ui and Amplify auth. Start with a basic client (login, chat, sessions, prompts, upgrade button), then the full one, including person management with a birth-place picker for Jyotisha charts backed by `GET /v1/places`.

## 13. Risks and open decisions

### Decisions to confirm before Phase 1

| Decision | Recommendation | Why it matters |
| --- | --- | --- |
| LLM provider | Amazon Bedrock | Affects IAM, cost, model choice and data residency |
| Ephemeris library | `jyotishganit` (MIT; Skyfield and NASA JPL DE421) | Replaces Swiss Ephemeris, so no copyleft licence is needed and the application is proprietary; see sections 2 and 14 |
| Web client | Swagger UI (Phase 1), Gradio test client (Phase 2), React with assistant-ui after the MVP | Defines CORS and token handling |
| CI/CD system | GitHub Actions with OIDC | Skip if your code lives elsewhere (GitLab, CodePipeline) |
| AWS region | `eu-central-1` (Frankfurt), decided | Fixes where data lives and which Bedrock models are available |
| AWS access for Phases 1 and 2 | Personal AWS account with access keys, decided | Only Bedrock and script-created `asternavium-local-*` DynamoDB tables; tests use moto. Replaced in Phase 3 by Organizations, IAM Identity Center and Terraform, following best practices |
| Lambda architecture | `arm64` (Graviton), decided | Lower price per GB-second; the image is built for `linux/arm64` on GitHub's arm64 runners |
| Datadog | EU site (`datadoghq.eu`), set up in Phase 5, decided | The site cannot be changed later without a new Datadog organisation; deferring keeps Datadog cost out of the early phases |
| Streaming responses | After the MVP | Better UX for long answers; adds SSE handling and client work |

Two further decisions follow from the module order:

- **Jyotisha settings:** ayanamsa, house system, dasha variant and the classical texts the interpretation rules follow.
- **Bukvitsa scope and sources (after the MVP):** which traditions, which languages, which sources count as reliable, and who reviews the content before the module launches.

### Risks

| Risk | Mitigation |
| --- | --- |
| LLM cost of free use grows faster than expected | Daily and monthly request limits from settings, token caps, cost metric per request, cheaper model for summaries, AWS budget alerts |
| Cold starts hurt chat latency | Container image trimmed with `uv`, lazy imports, provisioned concurrency if needed |
| `jyotishganit` is a young library (beta) whose releases have changed chart results | Exact version pin, golden tests before every upgrade, one adapter module, so it can be replaced by an own engine on Skyfield |
| Hallucinated astrological facts | Engines compute all positions and numbers; the model only explains tool output; evals check this |
| Sensitive personal data (birth date, time, place) | Minimal collection, encryption, deletion endpoint, no content in Datadog logs, consent text. Birth data of other people (relatives, clients) needs the user's confirmation that they may share it, a privacy policy that covers it, and deletion of each person on its own |
| Health, legal or financial advice requests | System prompt policy, refusal tests in the eval set, visible disclaimer in the product |
| Prompt injection through user input or profile fields | Treat inputs as data, restrict tools to the user's own data, scoped IAM |
| Scope creep into more traditions | New modules only after MVP; each needs reliable calculation methods and sources, as the project description requires |
| Birth villages missing from the bundled places dataset | GeoNames `cities500` keeps only places with a known population of 500 or more; in Ukraine that is about 5,400 of 33,700 populated places, because most villages have no population figure (e.g. Vlasivka in Kyiv Oblast). The MVP accepts this: the user picks the nearest town, with the right time zone and coordinates a few kilometres off. Before launch, reconsider Amazon Location Service Places (API v2, `geo-places`, available in `eu-central-1`), checked 2026-11-04: `Autocomplete` filtered to settlements ($0.20 per 1,000, results not storable, no coordinates or time zone) while typing, then one `GetPlace` with the time zone feature and `IntendedUse=Storage` ($4.00 per 1,000, needed because the profile keeps the coordinates and time zone) on selection, about $0.006 per birth place chosen. Open points: (1) decision D7, because AWS sends the query text to its data provider without account metadata and its service terms allow processing outside the AWS region, so the privacy policy must list it; (2) the time zone name is not documented as an IANA ID, so every returned name must load in `zoneinfo`; (3) coverage of Ukrainian villages and Cyrillic input is unverified. First step: a short spike with `geo-places:Autocomplete` and `geo-places:GetPlace` on the `asternavium-local` IAM user, querying villages missing from GeoNames. A hybrid is possible (GeoNames first, Amazon Location as a "can't find your town?" fallback); place IDs are opaque strings, so either option needs no data migration |
| City districts dropped from the bundled places dataset | GeoNames sections of populated places (`PPLX`, about 10,800 entries such as Kyiv's Obolon or Berlin Köpenick) are excluded, so a search for a city is not crowded by its districts and the user picks the city itself: same time zone, coordinates a few kilometres off. This also drops some large places coded as districts, such as Navi Mumbai and Kowloon, and does not catch districts GeoNames codes as ordinary places, such as the Paris arrondissements. Confirm before launch whether to keep districts instead |

### Sources

- [Using DynamoDB as a checkpoint store for LangGraph agents](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ddb-langgraph-checkpoint.html), AWS documentation
- [Amazon API Gateway now supports response streaming for REST APIs](https://aws.amazon.com/about-aws/whats-new/2025/11/api-gateway-response-streaming-rest-apis), AWS, 19 Nov 2025
- [FastAPI response streaming example](https://github.com/awslabs/aws-lambda-web-adapter/blob/main/examples/fastapi-response-streaming), AWS Lambda Web Adapter project

* [AWS App Runner availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html), AWS documentation
* [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/), AWS

- [jyotishganit](https://github.com/northtara/jyotishganit), NorthTara Research, MIT licence

Other statements (Cognito, SES) come from general knowledge as of October 2026 and were not re-checked against vendor pages; verify prices, quotas and license terms before committing.

## 14. Licence and third-party notices

AsterNavium is proprietary software (all rights reserved). It was published under the AGPL-3.0 while Swiss Ephemeris was the planned engine, because the free Swiss Ephemeris licence is the AGPL; that requirement ended with the switch to `jyotishganit` (section 2). This section is an engineering checklist, not legal advice; have a lawyer review it before launch.

### In the repository

- **`LICENSE`** at the root of `asternavium`: a proprietary notice, all rights reserved. It names "AsterNavium contributors" as the copyright holder for now; before launch (Phase 7), name a real person or company in `LICENSE` and `NOTICE`, because only an identifiable holder can grant permission and enforce the rights.
- **Licence metadata:** the `license` field in `pyproject.toml` marks the package as proprietary. The per-file `SPDX-License-Identifier` headers and their pre-commit check are removed; `LICENSE` covers every file.
- **`NOTICE`** lists the third-party packages with their licences (MIT, BSD and Apache-2.0 require keeping their copyright notices in anything distributed, including the container image) and the data attributions: GeoNames places data (CC-BY 4.0), NASA JPL DE421 ephemeris (public domain, credited) and the Hipparcos catalogue (ESA, credited).
- **Repository visibility:** private. Versions published earlier under the AGPL-3.0 stay under that licence for anyone who obtained them; later versions do not.

### In the running service

- `GET /v1/about` returns the version and commit SHA, without the source URL, and the data attributions; Swagger UI shows no open-source licence.
- The GeoNames attribution is visible wherever place search is offered (CC-BY 4.0 requires credit when the data is shared through the API).

### Rules to keep

- Check every new dependency's licence before adding it: permissive licences (MIT, BSD, Apache-2.0) are fine; copyleft licences (GPL, AGPL) are not, for anything in the image, because they would again require publishing the source. A licence scan in CI fails the build on them.
- No secrets, keys, account IDs or user data in the repository, even though it is private: secret scanning in pre-commit and CI, values in Secrets Manager.
- Before anyone else contributes, agree in writing who owns their contributions (an assignment or a contributor licence agreement).

### Decisions before launch

| Item | Question | Default |
| --- | --- | --- |
| Terraform repo | Public or private? | Private, like the application |
| Bukvitsa service (after the MVP) | Its licence and the licence of its content | Decided with the module; a separate service in its own repository |
| Web client | Licence | Proprietary, like the application |
| Gradio test client | Lives in the app repo | Proprietary with the rest |
