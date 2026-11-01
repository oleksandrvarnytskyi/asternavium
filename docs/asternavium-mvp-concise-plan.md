# AsterNavium MVP: Concise Implementation Plan

Oct 22, 2026

The AsterNavium MVP ships as an API-first, subscription-based AI chat over two modules (Jyotisha and Bukvitsa, the Slavic symbolic traditions) on a serverless AWS stack. Western astrology is the next module, then others; the platform's modular shape means none of them needs a redesign. Technical detail is in the detailed specification (`asternavium-mvp-specification.md`).

## 1. What the MVP takes from the platform vision

| Platform element | In the MVP | After the MVP |
| --- | --- | --- |
| Astrology systems | Jyotisha: sidereal birth chart, nakshatras, dasha periods | Western astrology, other regional traditions, transits, compatibility |
| AI-assisted interpretation | LangGraph agent that explains tool results; answers separate calculated, traditional and AI-generated parts | Comparative answers across traditions |
| Personal profiles and reports | Profile (birth data, language, level); history saved per session | Formal reports, PDF export |
| Learning and exploration | Bubble prompts as guided entry points; glossary | Learning paths, quizzes, source references |
| Structured knowledge base | Curated glossary and prompts in the app repo; sourced Bukvitsa entries in their own service | Source library, retrieval (RAG) |
| Modular architecture | `domain/<module>` packages behind a `module` field | Western astrology, then other modules |
| Responsible AI | Disclaimer, transparency labels, no medical, legal or financial advice | Continuous evaluation |

## 2. MVP scope

- FastAPI project with layered structure; `POST /v1/chat` and `GET /v1/prompts`, plus session, profile, billing and notification endpoints
- Sign-in with OAuth2 and JWT through Amazon Cognito; plan-based authorization
- Multiple chat sessions; short-term memory (LangGraph checkpoints) and long-term history (DynamoDB)
- Free and premium plans with daily request quotas; Stripe subscriptions
- Email (SES) and push (FCM) notifications depending on the plan
- Terraform in a separate repo, CI/CD pipelines, Datadog and LangSmith monitoring

**Stack:** Python 3.13, `uv`, FastAPI, Pydantic, LangChain, LangGraph, LangSmith, Amazon Bedrock, Swiss Ephemeris, pytest, AWS Lambda (arm64), API Gateway, DynamoDB, Cognito, SQS, EventBridge, SES, Stripe, Terraform, Datadog, GitHub Actions.

**Modules, in order:** Jyotisha and Bukvitsa (Slavic symbolic traditions) in the MVP; Western astrology next; then other traditions.

**Clients:** FastAPI Swagger UI from Phase 1 (Cognito sign-in from Phase 5), a Gradio test client from Phase 2 (run locally until Phase 4, then hosted in dev only: Lambda first, with Fargate at 0.25 vCPU and 1 GB as the fallback); React with assistant-ui is parked for the production release after the MVP.

**Environments:** `dev` and `prod` in separate AWS accounts, both in `eu-central-1` (Frankfurt), each with its own Cognito, Stripe (test versus live), Datadog tags and pipeline. `dev` deploys on every merge; `prod` deploys on a release tag after manual approval. Phases 1 to 3 run locally, using a personal AWS account only for Bedrock and DynamoDB; the `dev` account, Terraform and pipelines arrive in Phase 4. All prod setup happens in Phase 8, after the MVP is implemented and tested in dev.

**Licence:** Swiss Ephemeris is used under the AGPL-3.0, so the application repository is public under the AGPL-3.0. Required: a `LICENSE` file with the full AGPL-3.0 text, a `NOTICE` file with the Swiss Ephemeris and third-party notices, a source link in the service (`GET /v1/about`, Swagger UI, client), AGPL-compatible dependencies only, and no secrets in the repository. Details are in section 14 of the detailed specification.

**Bukvitsa service:** the Slavic symbolic traditions run as a separate service, Bukvitsa, in its own repository (`asternavium-bukvitsa`): a read-only API over curated, sourced entries that the main API calls as an agent tool. Its content and licence stay independent of the AGPL application, subject to legal confirmation. It is built in Phase 3, after the core functionality, and deployed to `dev` in Phase 4.

## 3. Phases and exit criteria

Build order: core functionality first (data layer and sessions, chat and the Jyotisha engine, then Bukvitsa), developed and run locally; then the AWS foundation and first deploy of everything built so far; then authentication, observability and payments, notifications, then hardening. Until Phase 5, the API uses a temporary test identity instead of Cognito.

| Phase | Deliverables | Done when |
| --- | --- | --- |
| 0. Decisions and setup | Open decisions confirmed, Bukvitsa source curation started, repos, `uv` and CI skeleton, FastAPI skeleton, AGPL-3.0 licence files and source link | `make test` passes in CI |
| 1. Data layer and sessions (local) | Local DynamoDB tables in a personal AWS account, repositories, sessions API, profile, temporary dev identity, Swagger UI as first client | Sessions are per test user; cross-user access blocked |
| 2. AI core (local) | LangGraph agent, Jyotisha engine (Swiss Ephemeris), Bedrock in the personal AWS account, chat and prompts endpoints, LangSmith, Gradio test client run locally | Two parallel sessions each keep their own context |
| 3. Bukvitsa service (local) | Separate repo and CI, read-only API over sourced entries, client and agent tool, run locally | Bukvitsa questions get sourced answers; the agent copes with the service down |
| 4. Foundation and first deploy | AWS Organization and `dev` account, Terraform bootstrap and `dev` (API, data, Bukvitsa), image pipelines, CloudWatch logging, hosted Gradio client; the personal account is retired from the project | Everything from Phases 1 to 3 deploys from `main` to `dev`; JSON logs with request IDs in CloudWatch |
| 5. Authentication | Cognito, JWT validation, `GET /v1/me`, dev identity removed | Sign-up through hosted UI returns a profile |
| 6. Observability and monetization | Datadog (EU site: Lambda extension, APM tracing, first dashboard, cost-per-plan metrics), plans, quotas, Stripe checkout, portal and webhooks | Traces visible in Datadog; test-mode upgrade raises limits in under 30 seconds |
| 7. Notifications | SQS, EventBridge, SES, FCM, preferences | Premium user gets push and email; free user only allowed ones |
| 8. Hardening and launch | Monitors, load test, security review, legal texts, prod setup (account, Terraform environment, release pipeline, live-mode services) and promotion of the tested image to `prod` | Success criteria met in `prod` |

## 4. Decisions needed before starting

- LLM provider: Amazon Bedrock
- Payment provider: Stripe, with Paddle (merchant of record) as the fallback if your legal entity's country is not supported by Stripe; settle this before Phase 6
- Ephemeris license for Jyotisha charts: Swiss Ephemeris under the AGPL-3.0; the project is published under the AGPL
- CI/CD system: GitHub Actions with AWS OIDC (assumed)
- AWS region: `eu-central-1` (Frankfurt) for `dev` and `prod` (decided)
- AWS access for Phases 1 to 3: the developer's personal AWS account with access keys, used only for Bedrock and script-created `asternavium-local-*` DynamoDB tables in `eu-central-1`; tests use moto and never call AWS. Replaced in Phase 4 by AWS Organizations, IAM Identity Center and Terraform (decided)
- Lambda architecture: `arm64` (Graviton), lower price per GB-second than `x86_64` (decided)
- Datadog: EU site (`datadoghq.eu`), set up in Phase 6, after authentication; until then, JSON logs on the console locally (Phases 1 to 3), then CloudWatch Logs and the built-in Lambda and API Gateway metrics in `dev` (decided)
- Production web client (React with assistant-ui): who builds it, and when

* Jyotisha settings: ayanamsa, house system, dasha variant, source texts
* Bukvitsa scope: which traditions, languages and sources; expert review before launch

- What is published: the application repo is public under the AGPL-3.0; decide on the Terraform repo and the web client; the Bukvitsa service is separate (confirm its licence position with a lawyer)

Team size of one backend developer is assumed; phases run mostly in sequence. Bukvitsa content curation and the production web client need extra capacity.
