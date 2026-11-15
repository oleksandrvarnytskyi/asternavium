# AsterNavium MVP: Concise Implementation Plan

Oct 22, 2026

The AsterNavium MVP ships as an API-first, free AI chat over one module, Jyotisha, on a serverless AWS stack, with a limit of 8 chat requests per day and 30 per month per user. Bukvitsa (the Slavic symbolic traditions) and paid plans come after the MVP (decided Nov 12, 2026); Western astrology is the next module, then others; the platform's modular shape means none of them needs a redesign. Technical detail is in the detailed specification (`asternavium-mvp-specification.md`).

## 1. What the MVP takes from the platform vision

| Platform element | In the MVP | After the MVP |
| --- | --- | --- |
| Astrology systems | Jyotisha: sidereal birth chart, nakshatras, dasha periods | Western astrology, other regional traditions, transits, compatibility |
| AI-assisted interpretation | LangGraph agent that explains tool results; answers separate calculated, traditional and AI-generated parts | Comparative answers across traditions |
| Personal profiles and reports | Profile (birth data, language, level); history saved per session | Formal reports, PDF export |
| Learning and exploration | Bubble prompts as guided entry points; glossary | Learning paths, quizzes, source references |
| Structured knowledge base | Curated glossary and prompts in the app repo | Sourced Bukvitsa entries in their own service, source library, retrieval (RAG) |
| Modular architecture | `domain/<module>` packages behind a `module` field | Western astrology, then other modules |
| Responsible AI | Disclaimer, transparency labels, no medical, legal or financial advice | Continuous evaluation |

## 2. MVP scope

- FastAPI project with layered structure; `POST /v1/chat` and `GET /v1/prompts`, plus session, person, profile and notification endpoints
- Sign-in with OAuth2 and JWT through Amazon Cognito; ownership checks and usage limits
- Multiple chat sessions; short-term memory (LangGraph checkpoints) and long-term history (DynamoDB)
- Free use for everyone: 8 chat requests per day and 30 per month per user
- Email notifications (SES), at most 30 per user per month
- Terraform in a separate repo, CI/CD pipelines, Datadog and LangSmith monitoring

**Stack:** Python 3.13, `uv`, FastAPI, Pydantic, LangChain, LangGraph, LangSmith, Amazon Bedrock, jyotishganit (Skyfield, NASA JPL DE421), pytest, AWS Lambda (arm64), API Gateway, DynamoDB, Cognito, SQS, EventBridge, SES, Terraform, Datadog, GitHub Actions.

**Modules, in order:** Jyotisha in the MVP; then Bukvitsa (Slavic symbolic traditions) and Western astrology; then other traditions.

**Clients:** FastAPI Swagger UI from Phase 1 (Cognito sign-in from Phase 4), a Gradio test client from Phase 2 (run locally until Phase 3, then hosted in dev only: Lambda first, with Fargate at 0.25 vCPU and 1 GB as the fallback); React with assistant-ui is parked for the production release after the MVP.

**Environments:** `dev` and `prod` in separate AWS accounts, both in `eu-central-1` (Frankfurt), each with its own Cognito, Datadog tags and pipeline. `dev` deploys on every merge; `prod` deploys on a release tag after manual approval. Phases 1 and 2 run locally, using a personal AWS account only for Bedrock and DynamoDB; the `dev` account, Terraform and pipelines arrive in Phase 3. All prod setup happens in Phase 7, after the MVP is implemented and tested in dev.

**Licence:** proprietary, all rights reserved, from Nov 12, 2026 (until then AGPL-3.0, required by the planned Swiss Ephemeris engine, which `jyotishganit` replaced). `NOTICE` keeps the third-party licence notices and data attributions (GeoNames, NASA JPL, Hipparcos), and every new dependency must have a permissive licence. Details are in section 14 of the detailed specification.

**Bukvitsa service (after the MVP):** the Slavic symbolic traditions will run as a separate service, Bukvitsa, in its own repository (`asternavium-bukvitsa`): a read-only API over curated, sourced entries that the main API calls as an agent tool. Its content and licence stay independent of the AGPL application, subject to legal confirmation. It is planned for after the MVP; its design is kept in section 3 of the detailed specification.

## 3. Phases and exit criteria

Build order: core functionality first (data layer and sessions, then chat with the Jyotisha engine), developed and run locally; then the AWS foundation and first deploy of everything built so far; then authentication, observability and usage limits, email notifications, then hardening. Until Phase 4, the API uses a temporary test identity instead of Cognito.

| Phase | Deliverables | Done when |
| --- | --- | --- |
| 0. Decisions and setup | Open decisions confirmed, Bukvitsa source curation started, repos, `uv` and CI skeleton, FastAPI skeleton, AGPL-3.0 licence files and source link | `make test` passes in CI |
| 1. Data layer and sessions (local) | Local DynamoDB tables in a personal AWS account, repositories, sessions API, profile, temporary dev identity, Swagger UI as first client | Sessions are per test user; cross-user access blocked |
| 2. AI core (local) | LangGraph agent, Jyotisha engine (jyotishganit), Bedrock in the personal AWS account, chat and prompts endpoints, LangSmith, Gradio test client run locally | Two parallel sessions each keep their own context |
| 3. Foundation and first deploy | AWS Organization and `dev` account, Terraform bootstrap and `dev` (API, data), image pipelines, CloudWatch logging, hosted Gradio client; the personal account is retired from the project | Everything from Phases 1 and 2 deploys from `main` to `dev`; JSON logs with request IDs in CloudWatch |
| 4. Authentication | Cognito, JWT validation, `GET /v1/me`, dev identity removed | Sign-up through hosted UI returns a profile |
| 5. Observability and usage limits | Datadog (EU site: Lambda extension, APM tracing, first dashboard, cost-per-request metrics), daily and monthly request limits, `Idempotency-Key` | Traces visible in Datadog; request 9 of a day and 31 of a month return `429` |
| 6. Notifications | SQS, EventBridge, SES, preferences, 30 emails per user per month | A user gets the welcome email and opted-in digests; email 31 of a month is not sent |
| 7. Hardening and launch | Monitors, load test, security review, legal texts, prod setup (account, Terraform environment, release pipeline, production services) and promotion of the tested image to `prod` | Success criteria met in `prod` |

## 4. Decisions needed before starting

- LLM provider: Amazon Bedrock
- Jyotisha engine: `jyotishganit` (MIT) instead of Swiss Ephemeris; the application is proprietary (decided Nov 12, 2026)
- CI/CD system: GitHub Actions with AWS OIDC (assumed)
- AWS region: `eu-central-1` (Frankfurt) for `dev` and `prod` (decided)
- AWS access for Phases 1 and 2: the developer's personal AWS account with access keys, used only for Bedrock and script-created `asternavium-local-*` DynamoDB tables in `eu-central-1`; tests use moto and never call AWS. Replaced in Phase 3 by AWS Organizations, IAM Identity Center and Terraform (decided)
- Lambda architecture: `arm64` (Graviton), lower price per GB-second than `x86_64` (decided)
- Datadog: EU site (`datadoghq.eu`), set up in Phase 5, after authentication; until then, JSON logs on the console locally (Phases 1 and 2), then CloudWatch Logs and the built-in Lambda and API Gateway metrics in `dev` (decided)
- Production web client (React with assistant-ui): who builds it, and when

* Jyotisha settings: ayanamsa, house system, dasha variant, source texts
* Bukvitsa scope (after the MVP): which traditions, languages and sources; expert review before the module launches

- What is published: nothing; the application, Terraform and web client repositories are private and proprietary; the Bukvitsa service, after the MVP, is separate (confirm its licence position with a lawyer)

Team size of one backend developer is assumed; phases run mostly in sequence. The production web client, and Bukvitsa content curation after the MVP, need extra capacity.
