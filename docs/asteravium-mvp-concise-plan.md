# AsterAvium MVP: Concise Implementation Plan

Oct 22, 2026

The AsterAvium MVP ships as an API-first, subscription-based AI chat over two modules (Jyotisha and Bukvitsa, the Slavic symbolic traditions) on a serverless AWS stack. Western astrology is the next module, then others; the platform's modular shape means none of them needs a redesign. Technical detail is in the detailed specification (`asteravium-mvp-specification.md`).

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

**Stack:** Python 3.13, `uv`, FastAPI, Pydantic, LangChain, LangGraph, LangSmith, Amazon Bedrock, Swiss Ephemeris, pytest, AWS Lambda, API Gateway, DynamoDB, Cognito, SQS, EventBridge, SES, Stripe, Terraform, Datadog, GitHub Actions.

**Modules, in order:** Jyotisha and Bukvitsa (Slavic symbolic traditions) in the MVP; Western astrology next; then other traditions.

**Clients:** FastAPI Swagger UI from Phase 2 (Cognito sign-in from Phase 5), a Gradio test client from Phase 3 (dev only; hosted on Lambda first, with Fargate at 0.25 vCPU and 1 GB as the fallback); React with assistant-ui is parked for the production release after the MVP.

**Environments:** `dev` and `prod` in separate AWS accounts, each with its own Cognito, Stripe (test versus live), Datadog tags and pipeline. `dev` deploys on every merge; `prod` deploys on a release tag after manual approval.

**Licence:** Swiss Ephemeris is used under the AGPL-3.0, so the application repository is public under the AGPL-3.0. Required: a `LICENSE` file with the full AGPL-3.0 text, a `NOTICE` file with the Swiss Ephemeris and third-party notices, a source link in the service (`GET /v1/about`, Swagger UI, client), AGPL-compatible dependencies only, and no secrets in the repository. Details are in section 14 of the detailed specification.

**Bukvitsa service:** the Slavic symbolic traditions run as a separate service, Bukvitsa, in its own repository (`asteravium-bukvitsa`): a read-only API over curated, sourced entries that the main API calls as an agent tool. Its content and licence stay independent of the AGPL application, subject to legal confirmation. It is built in Phase 4, after the core functionality.

## 3. Phases and exit criteria

Build order: core functionality first (data layer, chat and the Jyotisha engine), then Bukvitsa, then authentication, payments and notifications, then hardening. Until Phase 5, `dev` uses a temporary test identity instead of Cognito.

| Phase | Deliverables | Done when |
| --- | --- | --- |
| 0. Decisions and setup | Open decisions confirmed, Bukvitsa source curation started, AWS accounts, repos, `uv` and CI skeleton | `make test` passes in CI |
| 1. Foundation and first deploy | Terraform bootstrap and `dev`, FastAPI skeleton, image pipeline, Datadog, prod skeleton with approval gate, AGPL-3.0 licence files and source link | `/health` deploys from `main`, traces visible |
| 2. Data layer and sessions | DynamoDB table, repositories, sessions API, profile, temporary dev identity, Swagger UI as first client | Sessions are per test user; cross-user access blocked |
| 3. AI core | LangGraph agent, Jyotisha engine (Swiss Ephemeris), chat and prompts endpoints, LangSmith, Gradio test client | Two parallel sessions each keep their own context |
| 4. Bukvitsa service | Separate repo and pipeline, read-only API over sourced entries, client and agent tool | Bukvitsa questions get sourced answers; the agent copes with the service down |
| 5. Authentication | Cognito, JWT validation, `GET /v1/me`, dev identity removed | Sign-up through hosted UI returns a profile |
| 6. Monetization | Plans, quotas, Stripe checkout, portal and webhooks | Test-mode upgrade raises limits in under 30 seconds |
| 7. Notifications | SQS, EventBridge, SES, FCM, preferences | Premium user gets push and email; free user only allowed ones |
| 8. Hardening and launch | Monitors, load test, security review, legal texts, `prod` | Success criteria met in `prod` |

## 4. Decisions needed before starting

- LLM provider: Amazon Bedrock
- Payment provider: Stripe, with Paddle (merchant of record) as the fallback if your legal entity's country is not supported by Stripe; settle this before Phase 6
- Ephemeris license for Jyotisha charts: Swiss Ephemeris under the AGPL-3.0; the project is published under the AGPL
- CI/CD system: GitHub Actions with AWS OIDC (assumed)
- Production web client (React with assistant-ui): who builds it, and when

* Jyotisha settings: ayanamsa, house system, dasha variant, source texts
* Bukvitsa scope: which traditions, languages and sources; expert review before launch

- What is published: the application repo is public under the AGPL-3.0; decide on the Terraform repo and the web client; the Bukvitsa service is separate (confirm its licence position with a lawyer)

Team size of one backend developer is assumed; phases run mostly in sequence. Bukvitsa content curation and the production web client need extra capacity.
