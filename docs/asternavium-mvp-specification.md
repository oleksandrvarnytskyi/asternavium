# AsterNavium MVP: Specification and Step-by-Step Implementation

Oct 22, 2026

The MVP delivers an authenticated, subscription-gated AI chat on top of two knowledge modules: Jyotisha (Vedic astrology, with calculation tools) and Bukvitsa for Slavic symbolic traditions (curated, source-based knowledge), running serverless on AWS. The order after that is set: Western astrology and numerology come next, then other traditions, learning paths and comparative reports.

## 1. MVP scope

### In scope

- FastAPI project with a clean, layered structure
- Two core endpoints: `POST` chat (assistant ↔ user) and `GET` bubble prompts (starter questions), plus the supporting endpoints listed in section 5
- User authentication (OAuth2 + JWT) and authorization (roles, plans, entitlements)
- Multiple chat sessions per user
- Short-term memory (working context of an active session)
- Long-term memory (full chat history and profile in DynamoDB)
- Email and push notifications that depend on the subscription plan
- Monetization: free and paid tiers, request quotas, subscription payments
- Infrastructure as code in a separate Terraform repo, CI/CD pipelines, Datadog monitoring

### MVP modules

| Module | Nature | MVP content (confirm exact scope) |
| --- | --- | --- |
| Jyotisha | Calculation + interpretation | Sidereal birth chart, nakshatras, planetary periods (dasha), interpretation by documented classical rules |
| Bukvitsa (Slavic symbolic traditions) | Source-based knowledge, separate service | Curated, sourced entries on symbols, calendar and traditional concepts, each with its source and reliability noted; no invented calculation rules |

Next in order: Western astrology and numerology, then further traditions.

### Out of scope (post-MVP)

- Western astrology and numerology modules (the next modules after the MVP), then other traditions
- Learning paths, quizzes, comparative reports across traditions
- Retrieval over a knowledge base (RAG, vector search); MVP reads curated, versioned knowledge files through lookup tools instead
- Native mobile apps and the production web frontend (React with assistant-ui is parked until after the MVP; the MVP is API-first and uses Swagger UI and a Gradio test client)
- PDF reports, admin UI, referral or credit-pack pricing

### Assumptions to confirm

- Until the production web client exists, the API is exercised through Swagger UI (from Phase 1) and a Gradio test client (from Phase 2).
- Launch language is English; the assistant can answer in the user's language, but the glossary and prompts are English-only.
- Team of one backend developer; the production web client and Bukvitsa content curation need extra capacity.

### Success criteria

- A new user can sign up, ask a question and get an answer that clearly separates calculated results, traditional interpretation and AI explanation.
- Conversations persist and resume across sessions and devices.
- Free-tier quotas are enforced on every request; an upgrade is reflected in under 30 seconds after the payment webhook.
- p95 chat latency under 10 seconds (non-streaming), error rate under 1%.
- The whole environment can be rebuilt from the Terraform repo and the app pipeline with no manual steps.

## 2. Technology stack

Your proposed stack holds up. The main additions are Amazon Cognito for OAuth2/JWT, Stripe for billing, SQS plus EventBridge for notifications, and LangGraph (not just LangChain) for the agent and its short-term memory.

| Area | Choice | Notes |
| --- | --- | --- |
| Language, packaging | Python 3.13, `uv` | One `pyproject.toml` and `uv.lock`; `uv` also builds the Lambda image |
| API framework | FastAPI, Pydantic v2, pydantic-settings | Typed schemas, OpenAPI docs, settings from env |
| AI orchestration | LangChain + LangGraph | LangChain for models, prompts, tools; LangGraph for the agent graph, state and checkpointing |
| LLM provider | Amazon Bedrock, swappable via LangChain | IAM auth, no API keys, data stays in AWS. Direct Anthropic/OpenAI API is the alternative |
| LLM observability | LangSmith | Traces, prompt versions, datasets and evals |
| Compute | AWS Lambda (container image, `arm64`) + Lambda Web Adapter | FastAPI runs unchanged; image avoids the zip size limit that LangChain dependencies hit; Graviton (`arm64`) costs less per GB-second than `x86_64` |
| Region | `eu-central-1` (Frankfurt) | Both AWS accounts; check Bedrock model availability there before Phase 3 |
| API entry | API Gateway (REST API) | Supports response streaming since Nov 2025, so SSE chat is possible later |
| Authentication | Amazon Cognito user pool | OAuth2 authorization code + PKCE, social login, JWT access tokens |
| Database | DynamoDB, on-demand | Single-table design for app data; separate table for LangGraph checkpoints |
| Payments | Stripe Billing | Checkout, Customer Portal, webhooks. Fallback: Paddle as merchant of record (see section 13) |
| Email | Amazon SES | Transactional and digest emails |
| Push | Firebase Cloud Messaging | Covers web and mobile; SNS mobile push does not cover browsers |
| Async, scheduling | SQS, EventBridge Scheduler, Lambda workers | Notification fan-out, retries, dead-letter queue |
| Secrets, config | Secrets Manager, SSM Parameter Store | Stripe, LangSmith, FCM keys; non-secret config |
| IaC | Terraform in a separate repo | S3 remote state with native locking; modules + `dev`/`prod` environments |
| CI/CD | GitHub Actions with AWS OIDC (assumed) | No long-lived AWS keys. CodePipeline is the alternative |
| Monitoring | Datadog, EU site (`datadoghq.eu`) | Lambda extension, `ddtrace`, JSON logs; monitors and dashboards via the Datadog Terraform provider. Set up in Phase 6, after authentication; until then, local console logs (Phases 1 to 3), then CloudWatch Logs and the built-in Lambda and API Gateway metrics |
| Quality | pytest, pytest-asyncio, httpx, moto, ruff, mypy, pre-commit | Fake chat models for deterministic LLM tests |

**Web clients:** FastAPI's built-in Swagger UI from Phase 1 (Cognito sign-in from Phase 5), a Gradio test client from Phase 2 (local, then `dev` only from Phase 4), and React with assistant-ui for the production release after the MVP.

### Key decisions

- **Cognito instead of a hand-built OAuth2 server.** It already issues and rotates JWTs, handles social login, password reset and MFA. FastAPI only validates tokens via the JWKS endpoint. Building your own OAuth2 provider is the main security risk to avoid in an MVP.
- **LangGraph over plain LangChain chains.** You need stateful sessions, tool calls to calculation engines, and resumable threads. LangGraph checkpoints give per-session short-term memory out of the box.
- **Lambda container image.** LangChain, boto3 and an ephemeris library easily exceed 250 MB unzipped. Add provisioned concurrency only if cold starts hurt.
- **DynamoDB through `boto3` in a worker thread.** Repository methods are `async` and run their synchronous `boto3` calls with `anyio.to_thread`, so the event loop never blocks. `aioboto3` was not chosen: moto's in-process mock and `langgraph-checkpoint-aws` are built on `boto3`, and the checkpointer uses the same thread pattern (decided in Phase 1).
- **DynamoDB for both memories.** AWS documents a `DynamoDBSaver` in `langgraph-checkpoint-aws` with TTL, compression and optional S3 offload for large checkpoints; no Redis or VPC is needed in the MVP.
- **Ephemeris licensing.** Swiss Ephemeris (`pyswisseph`) is dual-licensed AGPL or paid professional. A closed-source SaaS needs the professional license, or an alternative such as JPL data via Skyfield. Use Swiss Ephemeris under its free AGPL licence. The project must then be published under the AGPL-3.0 or a compatible licence, with the AGPL-3.0 licence text in the repository and a way for users of the service to get the source; section 14 lists the required steps. The choice must be made before the public service goes live. Record the Jyotisha settings (ayanamsa, house system, dasha variant) as documented module assumptions.

* **Bukvitsa module is knowledge-first.** The Slavic symbolic traditions it covers are unevenly documented and often reconstructed, so the module serves curated, sourced entries with their reliability noted, and the agent must not invent calculation rules. This follows the platform principle that a module starts only with clear source material and scope. It runs as a separate service with its own repository, deployment and data, which the main API calls through an agent tool, so its content and licence can stay independent of the AGPL-licensed application (confirm this with a lawyer).

## 3. Architecture

*Diagram (see the live document):* the web client calls API Gateway (WAF, rate limits), which invokes one FastAPI Lambda containing the LangGraph agent and the Jyotisha engine. The Lambda uses Amazon Cognito (login, JWT), DynamoDB (history and memory), Amazon Bedrock (LLM), Stripe (billing, webhooks) and the Bukvitsa service. A separate asynchronous notification path runs EventBridge Scheduler → SQS + DLQ → Worker Lambda → Amazon SES (email) and Firebase FCM (push). Datadog and LangSmith observe every function.

A chat request enters through API Gateway, is authenticated with a Cognito JWT, and runs the LangGraph agent inside one FastAPI Lambda, which reads and writes DynamoDB and calls the LLM. Stripe webhooks arrive through the same API; notifications run on a separate asynchronous path.

There are three repositories: `asternavium` (application code and the image pipeline) and `asternavium-infra` (Terraform). The third, asternavium-bukvitsa, holds the Bukvitsa knowledge service, which the API calls over HTTPS. Terraform owns the infrastructure; the application pipelines only ship new images.

### Bukvitsa service

The Bukvitsa module, covering the Slavic symbolic traditions, is a separate service, so its content, release cycle and licence do not depend on the main application.

- **Interface:** a small read-only HTTPS API over curated entries (search by keyword or topic, get one entry by ID). Each entry returns its text, language, sources and a note on how reliable the source is, so the agent can cite it and separate source-based statements from interpretation.
- **Calling it:** the main API has a `bukvitsa_client` in `integrations/` and exposes it to the agent as a tool. Calls use IAM authentication or a service key, with a short timeout; if the service is down, the agent says the Bukvitsa content is unavailable instead of inventing an answer.
- **Hosting (MVP):** runs locally while it is built in Phase 3; from Phase 4, the same pattern as the main API: Lambda container image with its own pipeline and Terraform module in the infra repo, in `dev` first (`prod` follows in Phase 8). Start with versioned, validated content files bundled with the service; move to a database or retrieval later if the library outgrows that.
- **Content quality:** a schema check in CI rejects entries without a source; the content version is returned with every response.
- **Licensing:** the service uses no Swiss Ephemeris code and talks to the main API only over HTTPS, so it is generally treated as a separate work. That is a legal question, not a certainty; see section 14.

## 4. FastAPI project structure

The app repo (`asternavium`) uses a `src/` layout with strict layering: routers call services, services call repositories, agents and integrations, and the calculation engines in `domain/` stay pure Python with no AWS or LLM imports. That separation is what lets new traditions be added as modules later.

```
asternavium/
├── pyproject.toml            # uv-managed, ruff + mypy + pytest config
├── uv.lock
├── Dockerfile                # Lambda container image + Lambda Web Adapter
├── LICENSE                   # full AGPL-3.0 text (required)
├── NOTICE                    # Swiss Ephemeris + third-party licence notices
├── Makefile                  # lint, test, run, build, deploy shortcuts
├── .pre-commit-config.yaml
├── .github/workflows/        # ci.yml (PR), deploy.yml (main)
├── src/app/
│   ├── main.py               # create_app() factory, middleware, error handlers
│   ├── core/                 # config.py (pydantic-settings), logging.py, errors.py, security.py
│   ├── api/
│   │   ├── deps.py           # current_user, entitlements, service providers
│   │   └── v1/               # router.py, chat.py, prompts.py, sessions.py, me.py,
│   │                         # billing.py, notifications.py, webhooks.py, health.py
│   ├── schemas/              # Pydantic request/response models
│   ├── services/             # chat, sessions, quota, billing, notifications
│   ├── agents/               # LangGraph graph, prompts, tools, memory (checkpointer)
│   ├── domain/               # modules: jyotisha/ (engine); later western/, numerology/
│   ├── repositories/         # DynamoDB access: users, sessions, messages, subscriptions, devices
│   ├── integrations/         # llm_factory, stripe_client, ses_client, push_client, bukvitsa_client
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
- Dependency injection through `Depends` so tests can swap repositories, the LLM and Stripe for fakes.
- One error model (`{code, message, request_id}`) and a global exception handler; no stack traces to clients.
- Request ID middleware; structured JSON logging that carries `request_id`, `session_id`, hashed `user_id` and, from Phase 6, the Datadog trace ID.
- Lambda functions share one image: the API function and the workers differ only by command or handler.

## 5. API design

The two endpoints you named stay the core. Multiple sessions, billing and notifications need a few more routes, all small. Login itself is handled by Cognito's hosted UI (authorization code + PKCE), so the API has no login endpoint.

| Method, path | Auth | Purpose |
| --- | --- | --- |
| `GET /v1/prompts` | Public | Bubble prompts for the start screen. Query: `locale`, `module`. Static JSON, cacheable, so it is fast for anonymous visitors |
| `POST /v1/chat` | JWT + quota | Send a message. Body: `session_id` (optional, new session if omitted), `message`, `module`, `person_id` (for a new Jyotisha session: the person whose chart it is about, from `GET /v1/persons`; defaults to the user's own person; stored on the session and fixed for its lifetime), `locale`, `answer_depth` (optional, `simple`, `detailed` or `technical`; overrides the profile's default for this answer, which falls back to `simple` without a profile). Returns `session_id`, `message_id`, `reply`, `references`, `usage` and remaining quota |
| `GET /v1/me` | JWT | User ID and profile (from Phase 1; `profile` is `null` until the first `PUT /v1/profile`); plan, entitlements and remaining quota are added in Phases 5 and 6 |
| `DELETE /v1/me` | JWT | Delete the account and all its data (profile, persons, sessions, messages); idempotent |
| `PUT /v1/profile` | JWT | Traditions the user is interested in (one or more, unordered), language, answer depth (default depth of answers) and, optionally, which of the user's persons is the user (`owner_person_id`) |
| `GET` / `POST /v1/persons` | JWT | List or add the people the user makes charts for (the user, relatives, clients): a label and birth data (date, time to the minute, place ID from `GET /v1/places`); paginated |
| `GET` / `PUT` / `DELETE /v1/persons/{id}` | JWT | Read, replace or delete one person; deleting is idempotent |
| `GET /v1/places` | JWT | Search birthplaces by name in a GeoNames city dataset bundled with the app; returns place ID, name, region, country and time zone. The server fills in coordinates and time zone from the chosen place, so no birth place is sent to an external service |
| `GET /v1/sessions` | JWT | List sessions (title, module, last activity), paginated |
| `GET /v1/sessions/{id}/messages` | JWT | Paginated history of one session |
| `PATCH` / `DELETE /v1/sessions/{id}` | JWT | Rename or delete a session (with its messages); deleting is idempotent |
| `POST /v1/billing/checkout` | JWT | Create Stripe Checkout session for a plan |
| `POST /v1/billing/portal` | JWT | Link to Stripe Customer Portal (cancel, card, invoices) |
| `POST /v1/webhooks/stripe` | Stripe signature | Subscription lifecycle events |
| `PUT /v1/notifications/preferences` | JWT | Email and push opt-ins by type |
| `POST` / `DELETE /v1/notifications/devices` | JWT | Register or remove a push token |
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

- **Request validation.** Message length cap (for example 2,000 characters); `module` is an enum (`jyotisha, bukvitsa`, `general`).
- **Response labels.** Each answer carries structured parts: `calculated` (engine output), `traditional` (source-based statements), `interpretation` (AI explanation). This implements the platform's transparency principle and lets the client style them differently.
- **Idempotency.** Optional `Idempotency-Key` header so a retried request does not consume quota twice.
- **Streaming (after the MVP).** `POST /v1/chat/stream` over SSE using the same service, enabled by API Gateway response streaming and Lambda Web Adapter.
- **Errors.** `401` unauthenticated, `403` feature not in plan, `429` quota exceeded (with reset time), `422` validation.

## 6. Authentication and authorization

Cognito authenticates; the API authorizes. Tokens prove who the user is, while the current plan and quota live in DynamoDB so that a payment change takes effect immediately instead of waiting for token expiry.

### Authentication flow

1. The client sends the user to the Cognito hosted UI (authorization code + PKCE); email/password plus Google and Apple sign-in.
2. Cognito returns an access token (JWT, about 1 hour) and a refresh token.
3. The client calls the API with `Authorization: Bearer <access_token>`.
4. FastAPI validates signature (cached JWKS), issuer, audience/client ID, expiry and `token_use=access`, then loads the user from `sub`.
5. A Cognito post-confirmation trigger (Lambda) creates the `USER#<sub>` profile and a free-plan record in DynamoDB.

If you prefer to own the OAuth2 flow in FastAPI (`OAuth2PasswordBearer` plus self-issued JWTs), it is feasible, but you then also build registration, password reset, email verification, refresh rotation and brute-force protection. That is a poor trade for an MVP.

### Authorization model

| Layer | Mechanism | Example |
| --- | --- | --- |
| Identity | JWT `sub`, Cognito groups | `admin` group for internal endpoints |
| Resource ownership | Check `USER#<sub>` owns the session or person on every session, message or person call | A user cannot read another user's session or person |
| Plan entitlements | Entitlement set derived from the subscription item | `chat.daily_limit`, `persons.max`, `module.comparative`, `notifications.push` |
| Quota | Atomic counter in DynamoDB per user per day | Free: request 11 of 10 returns `429` |

Implementation: FastAPI dependencies `get_current_user()` and `require_entitlement("notifications.push")`; services never trust client-supplied user IDs. Add an API Gateway usage plan or WAF rate rule per IP as a first line of defense against abuse.

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

1. Validate the JWT and load the user, plan and entitlements.
2. Check and increment the daily quota atomically (conditional `UpdateItem`).
3. Load or create the session; verify the user owns it.
4. Run the LangGraph agent with `thread_id = session_id`; the checkpointer restores short-term state.
5. Trim context to a token budget: system prompt, profile facts, rolling summary, last N messages.
6. The agent may call tools (Jyotisha engine, Bukvitsa lookup, glossary) and then composes the answer.
7. Persist the user message and the answer to long-term storage; update session title and `updated_at`.
8. Return the response with remaining quota; refund the quota unit if the LLM call fails.

### DynamoDB single-table design (app table)

| Item | PK | SK | Key attributes |
| --- | --- | --- | --- |
| Profile | `USER#<id>` | `PROFILE` | email, locale, traditions (string set), answer depth, owner person ID (the person who is the account owner) |
| Person | `USER#<id>` | `PERSON#<ulid>` | label, birth data (local date and time, place copied from the dataset, UTC instant), created, updated |
| Subscription | `USER#<id>` | `SUB` | plan, status, provider customer/subscription IDs, period end |
| Session | `USER#<id>` | `SESSION#<ulid>` | title, module, person ID (Jyotisha sessions, from Phase 2), created, updated, message count |
| Message | `SESSION#<id>` | `MSG#<ulid>` | role, content, tokens in/out, model, trace ID |
| Daily quota | `USER#<id>` | `QUOTA#<yyyy-mm-dd>` | count, TTL |
| Push device | `USER#<id>` | `DEVICE#<id>` | FCM token, platform |
| Notification prefs | `USER#<id>` | `NOTIFPREFS` | email and push opt-ins |
| Webhook event | `EVENT#<stripe_event_id>` | `v1` | processed at, TTL (idempotency) |

The app table is named `asternavium-<environment>-app`: `asternavium-local-app` for local development, `asternavium-dev-app` and `asternavium-prod-app` in the AWS environments; the name reaches the app through the `ASTERNAVIUM_APP_TABLE_NAME` setting. A GSI on the Stripe customer ID resolves webhook events to users; it is added in Phase 6, when the first query needs it (DynamoDB adds a GSI to an existing table without migration). ULIDs keep sessions and messages time-ordered, so listing newest first is a plain `Query`. Enable on-demand capacity, point-in-time recovery and KMS encryption. Account deletion removes every `USER#<id>` item and the user's sessions' messages (needed for GDPR).

## 8. Notifications (email and push)

Notifications are asynchronous and never block a chat request: producers put a message on SQS, a worker Lambda checks the user's plan and preferences, then sends through SES (email) or Firebase Cloud Messaging (push).

| Notification | Channel | Free | Premium |
| --- | --- | --- | --- |
| Welcome, receipts, payment failed, security | Email | Yes (always, transactional) | Yes |
| Weekly digest (cycles and highlights from the chart of the user's own person) | Email | Opt-in | Opt-in |
| Daily insight | Push | No | Opt-in |
| Significant transit or cycle alert | Push + email | No | Opt-in |
| Reply ready for a long-running request (post-MVP) | Push | No | Yes |

The plan split above is a proposal; the mechanism enforces whatever the table says through the `notifications.*` entitlements.

### Components

- **EventBridge Scheduler** fires per-user or hourly batch triggers (respecting the user's time zone) that enqueue notification jobs.
- **SQS queue + dead-letter queue** gives retries and visibility into failures.
- **Worker Lambda** loads the user, checks opt-in and entitlement, renders the template, sends, and records the result.
- **SES** with a verified domain, DKIM, SPF, DMARC; bounce and complaint events (SNS) suppress future sends.
- **FCM** tokens registered via `POST /v1/notifications/devices`; invalid tokens are removed when FCM reports them.
- Every email carries an unsubscribe link, which updates `NOTIFPREFS`. Downgrade or cancellation automatically stops premium-only notifications because the worker re-checks entitlements at send time.

SES starts in sandbox mode; request production access at the start of Phase 8, since approval can take a few days.

## 9. Monetization

A freemium model with a daily request quota and premium-only features. All numbers below are starting proposals to tune after the first users arrive.

| Feature | Free | Premium (monthly or annual) |
| --- | --- | --- |
| Chat requests per day | 10 | 150 (fair use) |
| Saved sessions, history retention | 5 sessions, 30 days | Unlimited, 12 months |
| Persons with birth charts (the user, relatives, clients) | 3 | 50 (fair use) |
| Modules | Jyotisha birth chart basics, Bukvitsa knowledge entries | Plus deeper Jyotisha interpretation (periods), the full Bukvitsa library, comparative explanations later |
| Answer depth | Standard | Extended, more sources and references |
| Notifications | Transactional email, opt-in weekly digest | Plus push, daily insight, alerts |
| Priority model tier | No | Yes |

### Payment flow (Stripe Billing)

1. `POST /v1/billing/checkout` creates a Stripe Checkout Session for a chosen price and returns its URL.
2. The user pays on Stripe's hosted page; no card data touches your servers.
3. Stripe calls `POST /v1/webhooks/stripe`. The handler verifies the signature, deduplicates by event ID, and updates the `SUB` item.
4. Events to handle: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`, `invoice.paid`.
5. Entitlements are derived from plan and status on each request; `past_due` keeps premium for a short grace period, `canceled` falls back to free at period end.
6. Cancel, change card and invoices go through the Stripe Customer Portal.

### Quota and cost control

- Every chat counts as one request; the quota item increments atomically and is refunded when the LLM call fails.
- Log tokens and estimated cost per request in the message item and as a Datadog metric, so the margin per plan is visible from day one.
- Cap input length, output tokens and tool-call loops per request.
- Later options: credit packs for one-off reports, pay-per-use above the premium cap.

## 10. Infrastructure and CI/CD

Infrastructure lives in its own repo (`asternavium-infra`) so that cloud changes have their own review and approval path. The infra repo and the service repos (asternavium and asternavium-bukvitsa) meet through one contract: Terraform creates the Lambda functions and outputs their names; each service pipeline only pushes images and updates its own function code.

```
asternavium-infra/
├── bootstrap/            # state bucket, GitHub OIDC roles (applied once, per account)
├── modules/
│   ├── api/              # ECR, Lambda, API Gateway, WAF, custom domain + ACM
│   ├── auth/             # Cognito user pool, app client, hosted UI domain, triggers
│   ├── data/             # DynamoDB app table, checkpoints table, KMS, backups
│   ├── notifications/    # SQS + DLQ, EventBridge Scheduler, worker Lambda, SES identity
│   ├── secrets/          # Secrets Manager entries, SSM parameters
│   ├── bukvitsa/         # Bukvitsa service: Lambda, content storage, access policy
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

The same image is promoted from `dev` to `prod`; only variables and secrets differ. All prod setup is done in the last phase (Phase 8), after the whole MVP is implemented and tested in dev. Terraform state and secrets are separate per environment. In the infra repo, pull requests run `plan` for both environments, and a merge applies `dev` automatically while `prod` waits for approval of the reviewed plan.

| Aspect | dev | prod |
| --- | --- | --- |
| AWS account | Own account | Own account |
| App deploy | Automatic on every merge to `main` | Release tag, manual approval, gradual alias shift |
| Cognito | Own user pool, test users | Own user pool, real users |
| Stripe | Test-mode keys and test webhook endpoint | Live-mode keys and live webhook endpoint |
| LLM, quotas | Cheaper model, low daily limits | Production model and limits |
| SES, FCM | SES sandbox with verified addresses, test FCM project | SES production access, production FCM project |
| Datadog, LangSmith | `env:dev` tag, separate LangSmith project | `env:prod` tag, separate project, content hidden |
| Swagger UI (`/docs`) | Enabled; dev identity until Phase 5, then Cognito sign-in | Disabled |
| Gradio test client | Enabled (dev only); Lambda first, Fargate as fallback | Not deployed by default; Fargate (0.25 vCPU, 1 GB) if it is ever needed |
| Data | Disposable | Point-in-time recovery, deletion protection |

## 11. Observability and testing

### Datadog and LangSmith

Datadog (EU site, `datadoghq.eu`) is set up in Phase 6, after authentication. Until then, the app's JSON logs, which already carry request IDs, go to the console while Phases 1 to 3 run locally, and to CloudWatch Logs from Phase 4, together with the built-in Lambda and API Gateway metrics.

- **Datadog:** the Lambda extension and `ddtrace` provide APM traces across API Gateway, Lambda, DynamoDB and outbound calls; logs are structured JSON with a shared request and trace ID.
- **Custom metrics:** `llm.tokens.input/output`, `llm.latency`, `llm.cost_estimate`, `quota.exceeded`, `stripe.webhook.failed`, `notifications.sent/failed`, `signups`, `upgrades`.
- **Monitors (as code):** 5xx rate, p95 latency, LLM error rate, DLQ depth above zero, webhook failures, Lambda throttles, DynamoDB throttles, daily cost anomaly.
- **LangSmith:** traces every agent run (prompts, tool calls, token use), holds prompt versions and an evaluation dataset of golden questions. Tag runs with `env`, `module` and `plan`.
- **Privacy:** never log message text or birth data to Datadog. For LangSmith, enable input/output hiding or anonymization in `prod` unless the privacy policy and user consent cover storing conversations there.

### Testing strategy

| Layer | Approach |
| --- | --- |
| Calculation engines | Pure unit tests with golden cases (known Jyotisha charts checked against a reference chart tool) |
| Services and repositories | pytest with `moto` or DynamoDB Local; table creation fixtures |
| API | `TestClient`/`httpx` with dependency overrides for auth, LLM and Stripe |
| Agent | LangChain fake chat models for deterministic graph tests; assert tool selection and response structure |
| Prompt quality | LangSmith evals on a golden dataset; non-blocking in CI at first, a gate later |
| Payments | Signed Stripe webhook fixtures, idempotency and out-of-order event tests |
| Infrastructure | `validate`, lint, scan, plan; post-deploy smoke test against `dev` |

Aim for 80% coverage on `services/` and `domain/`; do not chase coverage on glue code.

## 12. Step-by-step implementation

Nine phases. Phases 1 to 3 build the core functionality (data layer and sessions, chat and the Jyotisha engine, then the Bukvitsa service) and run it locally; Phase 4 sets up AWS and deploys everything built so far to `dev`; from then on, every phase ends with something deployed and testable in `dev`. After the foundation come authentication, observability and payments, notifications, then hardening. The phases assume one backend developer working mostly in sequence.

**Local development until Phase 4.** The app runs on the developer's machine against a personal AWS account, accessed with an access-key profile, in `eu-central-1`. That account is used only for Amazon Bedrock and for on-demand DynamoDB tables named `asternavium-local-*`, which a script in the app repository creates with the same keys, indexes and TTL as the Terraform `data` module will. Tests never call AWS: they use moto, and LLM tests use fake chat models. Phase 4 replaces this setup with AWS Organizations, IAM Identity Center and Terraform, following best practices, and retires the personal account from the project.

### Phase 0. Decisions and setup

1. Confirm the open decisions in section 13 (Stripe legal entity, Jyotisha settings, Bukvitsa source scope, CI system), and start curating Bukvitsa sources, which continues in parallel through Phase 3. Also decide what is published: the application repository goes public under the AGPL-3.0 (section 14), so the Terraform repo and the Bukvitsa service need an explicit decision on what is public and under which licence.
2. Create the repos, branch protection and PR templates.
3. `uv init`, ruff, mypy, pytest, pre-commit; Makefile with `lint`, `test`, `run`.
4. App skeleton: app factory, settings, JSON logging, error model, request ID middleware, `GET /health`, and `GET /v1/about` as the source link, with the AGPL-3.0 licence file and notices (section 14).

**Done when:** `make test` passes in CI.

### Phase 1. Data layer and sessions (local)

1. Local tables: a script creates the `asternavium-local-app` table (keys and TTL as in section 7; the Stripe customer GSI follows in Phase 6) in the personal AWS account; table names come from settings, so Phase 4 only changes configuration.
2. Repositories for profile, person, session and message; moto-based tests. The subscription and quota repositories move to Phase 6, where they are first used.
3. Session endpoints (list, history, rename, delete) with ownership checks; `GET /v1/me`, `PUT /v1/profile` and `DELETE /v1/me` (account deletion); persons endpoints for the birth data of the user and of other people; `GET /v1/places` for birthplaces.
4. Temporary `POST /v1/sessions` (module, optional title), so sessions can be created and the endpoints above tested before `POST /v1/chat` exists. It is removed in Phase 2.
5. Temporary dev identity: `get_current_user` reads a test user from an `X-Dev-User` header when the environment is `dev`, so sessions can be built and tested before Cognito exists. It is removed in Phase 5, and a test asserts it is disabled in `prod`.

**Done when:** sessions can be created and listed per test user, and cross-user access returns `404` (`204` for a delete, which changes nothing), so a session's existence is not revealed.

**Status:** done on Nov 11, 2026. The exit criteria were checked against the `asternavium-local-app` table with two test users, through HTTP calls and in Swagger UI. The detailed steps and decisions are in `phase-1-implementation-plan.md`.

**Web client from this phase:** Swagger UI (`/docs`), enabled in `dev` and disabled in `prod`. It uses the dev identity until Phase 5 adds the Cognito Authorize button.

### Phase 2. AI core: chat, prompts, memory (local)

1. LLM factory (`init_chat_model`) with Bedrock in the personal AWS account (model access enabled in `eu-central-1`); model and limits come from settings.
2. Jyotisha engine on Swiss Ephemeris (pyswisseph, or its community fork pysweph, which keeps the same import name): the library supplies planetary positions, sidereal modes and houses; the project adds nakshatras and dasha periods, validated with golden tests against a reference chart tool. The library is a C extension, so the Docker image in Phase 4 needs the C build tools.
3. LangGraph agent: system prompt that enforces the platform's transparency and disclaimer rules, tools for the Jyotisha engine and the glossary, `DynamoDBSaver` checkpointer on a local `asternavium-local-checkpoints` table (added to the table script), context trimming and summary. The Bukvitsa tool is added in Phase 3.
4. `POST /v1/chat` using the chat turn sequence from section 7 (the quota and plan checks arrive in Phase 6); `GET /v1/prompts` serving versioned bubble prompts. Remove the temporary `POST /v1/sessions` from Phase 1, so `POST /v1/chat` is the only way to create a session; tests that need a session create it through chat. A Jyotisha session stores the `person_id` it is about; deleting a person also deletes that person's sessions, because their history holds the person's chart.
5. LangSmith project, tracing, golden dataset (about 30 questions), first eval run.

**Done when:** a test user holds two parallel sessions, each remembers its own context, and history survives an app restart.

**Web client from this phase:** a Gradio test client in its own folder (`tools/gradio_client/`), run locally against the local API with the dev identity (a Cognito token from Phase 5). It is hosted in `dev` from Phase 4.

### Phase 3. Bukvitsa service (local)

1. New repository `asternavium-bukvitsa`: a small read-only API over curated, sourced entries (search, get one entry by ID); a schema check in CI rejects entries without a source. It runs locally next to the main API.
2. A `bukvitsa_client` in the main API and an agent tool that returns the entry with its source and reliability note; if the service is down, the agent says the content is unavailable instead of inventing an answer. Locally, calls use a service key from settings; the authentication used in AWS (IAM or service key) is decided in Phase 4.
3. Load the first curated content set agreed in Phase 0 and add Bukvitsa questions to the LangSmith golden dataset.

**Done when:** a Bukvitsa question in chat returns a sourced answer, and the agent degrades gracefully when the service is stopped.

### Phase 4. Foundation and first deploy

1. AWS setup: an AWS Organization with the `dev` account, an IAM Identity Center admin user with MFA and an SSO CLI profile, and a budget alert. This replaces the personal account's access keys for project work.
2. Infra repo: `bootstrap/` (state bucket, OIDC roles), then `dev` with ECR, Lambda, API Gateway and WAF; the `data` module (app table, checkpoints table, TTL, PITR, KMS; the Stripe customer GSI is added in Phase 6), which replaces the local table script; secrets; and the `bukvitsa` module. The API role reaches only its tables, its secrets and the chosen Bedrock models.
3. Dockerfile with Lambda Web Adapter (`arm64` image, with the C build tools for Swiss Ephemeris); pipeline builds, pushes and deploys the image. The Bukvitsa service gets its own image and pipeline the same way.
4. CloudWatch log groups with JSON logs that carry request IDs. Datadog is set up later, in Phase 6.
5. Gradio test client hosted in `dev`: try Lambda first (container image, Function URL with response streaming, reserved concurrency of 1) as a one-day spike. If Gradio's streaming or session state misbehaves there, fall back to Fargate with 0.25 vCPU and 1 GB, roughly $10 a month if always on and less with a schedule that stops it outside working hours (rates from a May 2026 article; check current AWS pricing). App Runner is not an option because AWS closed it to new customers. Running Gradio locally against the `dev` API stays the free alternative.
6. Retire the personal AWS account from the project: delete the `asternavium-local-*` tables and stop using its keys in project configuration.

**Done when:** a commit to `main` deploys the API to `dev`; `/health`, sessions, chat with Bedrock and Bukvitsa answers work there; and JSON logs with request IDs appear in CloudWatch.

**Dev only until the end:** everything related to `prod` is done in Phase 8, after the whole MVP is implemented and tested in `dev`.

### Phase 5. Authentication and authorization

1. Terraform `auth` module: Cognito user pool for dev, app client, hosted UI, Google and Apple identity providers, post-confirmation trigger (the prod pool is created in Phase 8).
2. JWT validation dependency with cached JWKS; `get_current_user`, group-based admin check.
3. `GET /v1/me` (in place since Phase 1) resolves the user from the token; tests with signed test tokens.
4. Replace the dev identity with Cognito and remove the `X-Dev-User` path. Wire Swagger UI's Authorize button to Cognito (authorization code + PKCE; register the Swagger redirect URL on the `dev` app client) and give the Gradio client a Cognito token.

**Done when:** a user signs up through the hosted UI, `GET /v1/me` returns their profile, and the dev identity no longer works anywhere.

### Phase 6. Observability and monetization

1. Datadog on the EU site (`datadoghq.eu`): Lambda extension and `ddtrace` in the image, Datadog trace IDs in the JSON logs, a Terraform `observability` module with the Datadog provider and a first dashboard, and the custom metrics for tokens and estimated cost per request (section 9), so the margin per plan is visible from the first paid user.
2. Define plans and entitlements in one config module; subscription and quota repositories; quota service with atomic counters and refunds; the Stripe customer GSI on the app table; plan, entitlements and remaining quota in `GET /v1/me`.
3. Stripe products and prices in test mode (or the Paddle equivalent if the fallback is chosen); `checkout`, `portal` and webhook endpoints with signature check and idempotency.
4. Enforce entitlements on chat, history length, modules and the number of persons; return `403`/`429` with clear codes.
5. End-to-end tests with the Stripe CLI and signed fixtures, including payment failure and cancellation.

**Done when:** traces and cost-per-plan metrics appear in Datadog, a test-mode upgrade raises the user's limits within 30 seconds, and cancellation lowers them at period end.

### Phase 7. Notifications

1. Terraform `notifications` module: SQS and DLQ, EventBridge Scheduler, worker Lambda, SES identity in sandbox mode (production access is requested in Phase 8).
2. Preferences and device endpoints; email templates; FCM integration.
3. Worker with plan re-check, bounce and unsubscribe handling; weekly digest and daily insight jobs.

**Done when:** a premium test user receives a push and an email, and a free user receives only the allowed ones.

### Phase 8. Hardening and launch

1. Datadog monitors and dashboards as code; alerting to the on-call channel; runbooks for webhook, DLQ and quota incidents.
2. Load test for the chat path; tune Lambda memory, timeouts and cold starts; decide on provisioned concurrency.
3. Security review: IAM, WAF rules, prompt-injection tests, secrets, dependency audit.
4. Privacy and legal: privacy policy, terms, astrology disclaimer, data deletion and export flow, LangSmith data handling, and a final AGPL compliance check (section 14).
5. Set up `prod`: create the `prod` AWS account (state, OIDC role), apply the `prod` Terraform environment (API, data, Cognito pool, notifications, Bukvitsa service), create the release pipeline with manual approval and gradual alias shift, and configure the live-mode services (Stripe live keys and webhook, SES production access requested at the start of this phase, production FCM project, Datadog and LangSmith `prod` settings). Promote the same image that passed testing in `dev`, run the smoke test, then switch Stripe to live mode.

**Done when:** the success criteria in section 1 are met in `prod`.

### After the MVP: next modules

1. Western astrology and Pythagorean numerology, each as its own `domain/` package and `module` value, reusing chat, memory, quotas and notifications unchanged.
2. Then other traditions, learning paths and comparative analysis across modules.

Production web client, in parallel with the module work: React with assistant-ui and Amplify auth. Start with a basic client (login, chat, sessions, prompts, upgrade button), then the full one, including person management with a birth-place picker for Jyotisha charts backed by `GET /v1/places`.

## 13. Risks and open decisions

### Decisions to confirm before Phase 1

| Decision | Recommendation | Why it matters |
| --- | --- | --- |
| LLM provider | Amazon Bedrock | Affects IAM, cost, model choice and data residency |
| Payment provider | Stripe | Stripe needs a legal entity in a supported country; third-party sources report Ukraine is not supported, so check stripe.com/global. Fallback: Paddle as merchant of record, which does not list Ukraine as unsupported (occupied regions excluded), verifies every seller, checks the product category, pays out monthly and also handles VAT. Settle this before Phase 6; only the billing layer would change |
| Ephemeris library | Swiss Ephemeris under the AGPL-3.0; the project is published under the AGPL | No licence fee, but the whole project must be AGPL-compatible and public; see section 14 |
| Web client | Swagger UI (Phase 1), Gradio test client (Phase 2), React with assistant-ui after the MVP | Defines CORS, token handling and push (web push needs a service worker) |
| CI/CD system | GitHub Actions with OIDC | Skip if your code lives elsewhere (GitLab, CodePipeline) |
| AWS region | `eu-central-1` (Frankfurt), decided | Fixes where data lives and which Bedrock models are available |
| AWS access for Phases 1 to 3 | Personal AWS account with access keys, decided | Only Bedrock and script-created `asternavium-local-*` DynamoDB tables; tests use moto. Replaced in Phase 4 by Organizations, IAM Identity Center and Terraform, following best practices |
| Lambda architecture | `arm64` (Graviton), decided | Lower price per GB-second; the image is built for `linux/arm64` on GitHub's arm64 runners |
| Datadog | EU site (`datadoghq.eu`), set up in Phase 6, decided | The site cannot be changed later without a new Datadog organisation; deferring keeps Datadog cost out of the early phases |
| Streaming responses | After the MVP | Better UX for long answers; adds SSE handling and client work |

Two further decisions follow from the module order:

- **Jyotisha settings:** ayanamsa, house system, dasha variant and the classical texts the interpretation rules follow.
- **Bukvitsa scope and sources:** which traditions, which languages, which sources count as reliable, and who reviews the content before launch.

### Risks

| Risk | Mitigation |
| --- | --- |
| LLM cost outruns subscription revenue | Quotas, token caps, cost metric per plan, cheaper model for simple turns |
| Cold starts hurt chat latency | Container image trimmed with `uv`, lazy imports, provisioned concurrency if needed |
| Hallucinated astrological facts | Engines compute all positions and numbers; the model only explains tool output; evals check this |
| Sensitive personal data (birth date, time, place) | Minimal collection, encryption, deletion endpoint, no content in Datadog logs, consent text. Birth data of other people (relatives, clients) needs the user's confirmation that they may share it, a privacy policy that covers it, and deletion of each person on its own |
| Health, legal or financial advice requests | System prompt policy, refusal tests in the eval set, visible disclaimer in the product |
| Webhook loss or reordering | Idempotent handler, event table, periodic reconciliation job against Stripe |
| Prompt injection through user input or profile fields | Treat inputs as data, restrict tools to the user's own data, scoped IAM |
| Scope creep into more traditions | New modules only after MVP; each needs reliable calculation methods and sources, as the project description requires |
| Birth villages missing from the bundled places dataset | GeoNames `cities500` keeps only places with a known population of 500 or more; in Ukraine that is about 5,400 of 33,700 populated places, because most villages have no population figure (e.g. Vlasivka in Kyiv Oblast). The MVP accepts this: the user picks the nearest town, with the right time zone and coordinates a few kilometres off. Before launch, reconsider Amazon Location Service Places (API v2, `geo-places`, available in `eu-central-1`), checked 2026-11-04: `Autocomplete` filtered to settlements ($0.20 per 1,000, results not storable, no coordinates or time zone) while typing, then one `GetPlace` with the time zone feature and `IntendedUse=Storage` ($4.00 per 1,000, needed because the profile keeps the coordinates and time zone) on selection, about $0.006 per birth place chosen. Open points: (1) decision D7, because AWS sends the query text to its data provider without account metadata and its service terms allow processing outside the AWS region, so the privacy policy must list it; (2) the time zone name is not documented as an IANA ID, so every returned name must load in `zoneinfo`; (3) coverage of Ukrainian villages and Cyrillic input is unverified. First step: a short spike with `geo-places:Autocomplete` and `geo-places:GetPlace` on the `asternavium-local` IAM user, querying villages missing from GeoNames. A hybrid is possible (GeoNames first, Amazon Location as a "can't find your town?" fallback); place IDs are opaque strings, so either option needs no data migration |
| City districts dropped from the bundled places dataset | GeoNames sections of populated places (`PPLX`, about 10,800 entries such as Kyiv's Obolon or Berlin Köpenick) are excluded, so a search for a city is not crowded by its districts and the user picks the city itself: same time zone, coordinates a few kilometres off. This also drops some large places coded as districts, such as Navi Mumbai and Kowloon, and does not catch districts GeoNames codes as ordinary places, such as the Paris arrondissements. Confirm before launch whether to keep districts instead |

Added risk from the module order: the Bukvitsa module depends on content curation, not code, so it can slip even if the platform is ready. Mitigation: start sourcing in Phase 0, agree a small first scope, label every entry with its source, and keep a reviewer in the loop.

### Sources

- [Using DynamoDB as a checkpoint store for LangGraph agents](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ddb-langgraph-checkpoint.html), AWS documentation
- [Amazon API Gateway now supports response streaming for REST APIs](https://aws.amazon.com/about-aws/whats-new/2025/11/api-gateway-response-streaming-rest-apis), AWS, 19 Nov 2025
- [FastAPI response streaming example](https://github.com/awslabs/aws-lambda-web-adapter/blob/main/examples/fastapi-response-streaming), AWS Lambda Web Adapter project

* [AWS App Runner availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html), AWS documentation
* [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/), AWS

- [Swiss Ephemeris licensing information](https://www.astro.com/swisseph/swephinfo_e.htm), Astrodienst AG

Other statements (Cognito, Stripe, SES, FCM, Swiss Ephemeris licensing) come from general knowledge as of October 2026 and were not re-checked against vendor pages; verify prices, quotas and license terms before committing.

## 14. Licence compliance (AGPL-3.0)

AsterNavium uses Swiss Ephemeris under its free AGPL licence. The licence choice must be made before the public service goes live. The consequence is that the project's source must be published under the AGPL-3.0 or a compatible licence, and users of the network service must be able to obtain it. This section is an engineering checklist, not legal advice; have a lawyer review it before launch.

### Required in the repository

- **`LICENSE` file** at the root of the application repository (`asternavium`) with the full AGPL-3.0 text.
- **Licence metadata:** SPDX identifier in `pyproject.toml` and an `SPDX-License-Identifier` header in each source file, checked by pre-commit. Confirm the exact AGPL version (for example `AGPL-3.0-or-later`) against the Swiss Ephemeris licence text you download.
- **`NOTICE` file** that keeps the Swiss Ephemeris copyright and licence notices (Astrodienst AG; authors Dieter Koch and Alois Treindl) and lists the licences of all other dependencies, generated in CI. It also carries the attribution for the bundled GeoNames places data (CC-BY 4.0).
- **README** with a Licence section, how to build and run the service, and the source URL.
- A **public** repository that contains everything needed to run the service: application code, Dockerfile, build and configuration files.

### Required in the running service

- **Source offer:** `GET /v1/about` returns the version, commit SHA and source URL; FastAPI `license_info` shows the licence in Swagger UI; the web client shows a visible "Source code" link.
- **Published code matches deployed code:** every release is built from a tagged commit in the public repository, and the image tag carries the commit SHA.

### Rules to keep

- Only AGPL-compatible dependencies (MIT, BSD and Apache-2.0 are fine; proprietary components are not). A licence scan in CI fails the build on anything incompatible.
- A public repository means no secrets, keys, account IDs or user data in it. Add secret scanning to pre-commit and CI, keep values in Secrets Manager, and review the Terraform variables before anything is published.
- Prompts and the glossary stored in the application repository are published too; the Bukvitsa content lives in its own service.
- With contributors, add a DCO or CLA if you want the option to relicense later.

### Decisions before publishing

| Item | Question | Default |
| --- | --- | --- |
| Terraform repo | Public or private? | Usually a separate work, so it can stay private, but strip account IDs and confirm with a lawyer |
| Bukvitsa service | Separate service in its own repo: public, or private? | Likely a separate work (no Swiss Ephemeris code, HTTPS-only link), so its content and licence can stay independent; confirm with a lawyer |
| Web client | Separate repo that only calls the API | Commonly treated as a separate work; publishing it under the AGPL too is the simplest safe choice |
| Gradio test client | Lives in the app repo | Published under the AGPL with the rest |

What this means for the business: anyone may legally copy and run the code. The protection is the brand, the curated content, the users and the speed of development, not the source code.
