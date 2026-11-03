# Phase 4 Implementation Plan: Foundation and First Deploy

Oct 29, 2026

This plan breaks Phase 4 of the MVP into ordered, verifiable steps. Scope and exit criteria come from the concise plan (`asternavium-mvp-concise-plan.md`, section 3) and the detailed specification (`asternavium-mvp-specification.md`, sections 3, 4, 7, 10, 11, 12 and 14). Phase 4 is `dev` only; everything related to `prod` is done in Phase 8. Datadog is set up in Phase 6, after authentication; this phase uses CloudWatch.

## 1. Goal and exit criterion

Phases 1 to 3 build sessions, the AI core and the Bukvitsa service and run them locally, against a personal AWS account used only for Bedrock and `asternavium-local-*` DynamoDB tables. Phase 4 moves all of it into a proper `dev` AWS account, managed by Terraform and deployed automatically from `main`, and retires the personal account from the project.

**Done when:** a commit to `main` deploys the API to `dev`; `/health`, sessions, chat with Bedrock and Bukvitsa answers work there; and JSON logs with request IDs appear in CloudWatch.

Concretely, all of the following hold:

1. Merging to `main` in `asternavium` builds an `arm64` image, pushes it to ECR tagged with the commit SHA, deploys it to the `dev` Lambda and passes a smoke test, with no manual steps. The same holds for `asternavium-bukvitsa`.
2. Through API Gateway, behind WAF: `GET /health` returns `200`, a test user can create and list sessions, and a chat message gets an answer from Bedrock, including a sourced Bukvitsa answer.
3. `GET /v1/about` returns the deployed commit SHA, matching the commit that triggered the deploy.
4. Requests appear in CloudWatch Logs as one JSON line per log record, carrying the same `request_id` that the response returned in `X-Request-ID`, including uvicorn's access log.
5. No AWS keys are stored in GitHub; all repositories authenticate to AWS through OIDC.
6. Project configuration no longer uses the personal AWS account, and its `asternavium-local-*` tables are deleted.

## 2. Expected starting point

| Item | Status at the start of Phase 4 |
| --- | --- |
| App skeleton: factory, settings, JSON logging, error model, request IDs, `/health`, `/v1/about`, licence files | Done in Phase 0 |
| Sessions, profile, repositories over DynamoDB, temporary dev identity | Done in Phase 1, running against `asternavium-local-app` |
| LangGraph agent, Jyotisha engine, chat and prompts endpoints, Gradio client, LangSmith | Done in Phase 2, running against Bedrock and `asternavium-local-checkpoints` in the personal account |
| Bukvitsa service, client and agent tool | Done in Phase 3, running locally |
| Infra repo: `bootstrap/` state bucket, `envs/dev`, CI with fmt, validate, TFLint, Trivy | Done, not applied |
| Infra repo: GitHub OIDC provider and roles for the infra and app repositories | Written on `feat/phase-4-foundation`, not committed or applied; needs a deploy role for `asternavium-bukvitsa` |
| `dev` account, ECR, Lambda, API Gateway, WAF, DynamoDB, secrets | To do |
| Dockerfiles, image pipelines, uvicorn access logs in JSON, hosted Gradio client | To do |

`envs/prod` already exists in the infra repo as an empty root module; it stays untouched until Phase 8.

## 3. Decisions

| Decision | Choice | Notes |
| --- | --- | --- |
| AWS region | `eu-central-1` (Frankfurt), decided | Set in `terraform.tfvars` and `backend.hcl` for `bootstrap/` and `envs/dev`, and as `AWS_REGION` in each repository's GitHub environment. Bedrock model access is enabled for the same models used locally in Phase 2 |
| Lambda CPU architecture | `arm64` (Graviton), decided | About 20% cheaper per GB-second than `x86_64`. Images are built for `linux/arm64`; GitHub's free `ubuntu-24.04-arm` runners build them natively for public repositories |
| Datadog | EU site (`datadoghq.eu`), set up in Phase 6, decided | No Datadog account, key or code in this phase |
| AWS access | Organizations, IAM Identity Center and SSO, decided | Replaces the personal account's access keys used in Phases 1 to 3 |
| Bukvitsa authentication in AWS | IAM (SigV4) (recommended) | The API's Lambda role signs requests, so there is no shared key to store or rotate; the local service key from Phase 3 stays for local runs only. The alternative is a service key in Secrets Manager |
| Custom domain for the `dev` API | Defer to Phase 8 (recommended) | The default `execute-api` URL is enough for `dev`; a domain needs DNS access and an ACM certificate |
| WAF in `dev` | Keep, with a small rule set (recommended) | The specification puts WAF in front of the API; adding it now means `prod` in Phase 8 reuses a tested module. Cost: $5 per web ACL plus $1 per rule per month, plus $0.60 per million requests |

## 4. Work breakdown

The steps run in order; within a step, items can be done in any order. Each step lists the repository it touches and how to check that it is done.

### Step 1. AWS accounts and access (manual, no code)

1. Create the management account (dedicated root email, root MFA, no root access keys) and an AWS Organization in it.
2. Create the `asternavium-dev` member account in the Organization; the `prod` account is added in Phase 8.
3. Enable IAM Identity Center; create your admin user with MFA and assign it to `asternavium-dev` with an administrator permission set.
4. Configure the CLI profile with `aws configure sso --profile asternavium-dev`, region `eu-central-1`.
5. Enable a monthly AWS Budget with an email alert (for example $20) on the `dev` account.
6. In the `dev` account, enable Bedrock model access in `eu-central-1` for the models the app uses.

**Done when:** `aws sts get-caller-identity --profile asternavium-dev` returns the `dev` account through SSO.

### Step 2. Bootstrap the `dev` account (`asternavium-infra`)

1. Apply `bootstrap/` with local state to create the state bucket (`terraform.tfvars` from the example). Keep `terraform.tfstate` outside git, or migrate it into the new bucket.
2. Finish the GitHub OIDC provider and roles already written on the feature branch, adding a fourth role for the Bukvitsa repository. Each role trusts only one repository and one GitHub environment:

   | Role | Trusted by | Permissions |
   | --- | --- | --- |
   | `asternavium-dev-infra-plan` | `asternavium-infra`, pull requests | Read-only, with data reads denied, plus state bucket lockfile writes |
   | `asternavium-dev-infra-apply` | `asternavium-infra`, environment `dev` | Administrator, but cannot change the bootstrap roles, OIDC provider or state bucket |
   | `asternavium-dev-app-deploy` | `asternavium`, environment `dev` | Push to its ECR repositories, deploy its Lambda functions, move their `live` aliases |
   | `asternavium-dev-bukvitsa-deploy` | `asternavium-bukvitsa`, environment `dev` | The same, for the Bukvitsa ECR repository and function only |

3. Output the role ARNs. They contain the account ID, so they go into GitHub environment variables, not into any repository.

**Done when:** `terraform plan` in `bootstrap/` shows no changes, and the four roles exist with trust policies limited to their repository and environment.

### Step 3. Infra pipeline (`asternavium-infra`)

1. Create GitHub environment `dev` in the infra repository with variables `AWS_REGION=eu-central-1`, `AWS_PLAN_ROLE_ARN` and `AWS_APPLY_ROLE_ARN`.
2. Extend `ci.yml` with a `plan` job for `envs/dev` on pull requests that posts the plan as a PR comment.
3. Add `apply.yml`: on merge to `main`, apply `envs/dev` with the apply role. The `backend.hcl` and `terraform.tfvars` values come from environment variables, since those files are not in git.
4. Use a concurrency group per environment so two applies never run at once (S3 lockfile locking is the second safeguard).

**Done when:** a pull request with a trivial change shows a plan comment, and merging it applies cleanly.

### Step 4. ECR repositories (`asternavium-infra`)

Lambda functions cannot be created before their images exist in ECR, so the `api` and `bukvitsa` modules are applied in two parts.

1. Create ECR repositories `asternavium-api`, `asternavium-bukvitsa` and `asternavium-gradio`: immutable tags, scan on push, and a lifecycle policy that keeps the last 30 images.
2. Instantiate them from `envs/dev` and apply.

**Done when:** the three repositories exist and their URIs are Terraform outputs.

### Step 5. Container images (`asternavium`, `asternavium-bukvitsa`)

1. Add a multi-stage `Dockerfile` to the app repository, for `linux/arm64`:
   - the build stage uses the `uv` image, installs the C build tools that Swiss Ephemeris needs, and runs `uv sync --locked --no-dev` into a virtual environment;
   - the runtime stage is `python:3.13-slim`, runs as a non-root user, and copies only the virtual environment, `src/` and the versioned data files;
   - a build argument sets `ASTERNAVIUM_COMMIT_SHA` inside the image, so every image reports its own commit and Terraform keeps sole control of the function configuration;
   - Lambda Web Adapter is copied from its public ECR image into `/opt/extensions/`, pinned to an exact version; readiness check on `/health`;
   - the command starts uvicorn with `--factory app.main:create_app` on the adapter's port.
2. Add `.dockerignore` (`.venv`, `.git`, tests, caches, `.env`) and `make build`.
3. Add a Docker build job to `ci.yml` on pull requests, on an `ubuntu-24.04-arm` runner, as the specification requires (section 10, application pipeline).
4. Do the same for the Bukvitsa service, and for the Gradio client in `tools/gradio_client/`.
5. Add Lambda Web Adapter to `NOTICE`: it is Apache-2.0, which is compatible with the AGPL-3.0.

**Done when:** the images build in CI, and locally `docker run` with the required env variables answers `GET /health` for the API and Bukvitsa.

### Step 6. Logging for CloudWatch (`asternavium`)

The app already writes JSON logs with request IDs to stdout, and Lambda forwards stdout to CloudWatch Logs. Two gaps remain.

1. Route uvicorn's own loggers (`uvicorn`, `uvicorn.access`, `uvicorn.error`) through the JSON formatter, by passing a `log_config` to uvicorn, so access logs are JSON and carry the request ID too.
2. Add the commit SHA to every log line, so a log can be traced to the deployed build without Datadog.
3. Tests: access log lines are valid JSON with `request_id`, and no log line contains request bodies, query values or birth data.

**Done when:** running the image locally prints only JSON lines, including the access log, for a request to `/health`.

### Step 7. Data and secrets (`asternavium-infra`)

1. Create `modules/data`: the app table (`asternavium-dev-app`, following the naming convention in section 7 of the specification) and the checkpoints table with the same keys, GSI and TTL as the local table script from Phases 1 and 2, plus what the script leaves out: point-in-time recovery, KMS encryption and deletion protection off for `dev`.
2. Create `modules/secrets`: Secrets Manager containers for the LangSmith API key and any other keys the app uses. Terraform creates them empty; you set the values with the AWS CLI so they never enter Terraform state.
3. Outputs: table names and secret ARNs, consumed by the `api` module in step 8.
4. Delete the local table script from the app repository, or reduce it to a helper for running against moto, so there is one authoritative table definition.

**Done when:** both tables and the secret containers exist in `dev`, and the table definitions match what the app's repositories expect.

### Step 8. API: Lambda, API Gateway, WAF (`asternavium-infra`)

1. Lambda:
   - container image from ECR, `architectures = ["arm64"]`, 1024 MB memory and a 30-second timeout as a starting point; adjust once chat latency is measured;
   - `ignore_changes` on `image_uri`, because the app pipeline owns deployments;
   - a `live` alias, which API Gateway invokes, so rolling back means moving the alias;
   - env variables: `ASTERNAVIUM_ENVIRONMENT=dev`, `ASTERNAVIUM_SOURCE_URL`, table names, secret ARNs, the Bedrock model IDs, and the Bukvitsa endpoint;
   - an execution role that can write its own logs, read and write only its two tables, read only its secrets, invoke only the chosen Bedrock models, and call the Bukvitsa service;
   - a CloudWatch log group with 14-day retention and JSON log format.
2. API Gateway REST API: a `{proxy+}` resource and the root, both proxied to the `live` alias, a `dev` stage, throttling limits, and JSON access logs in their own log group, without request bodies. REST rather than HTTP API, because only REST supports WAF and response streaming.
3. WAF web ACL on the stage: AWS managed common rule set, known bad inputs, and a rate-based rule per IP.
4. Outputs: function name, alias name, API base URL. They go into the app repository's GitHub environment variables.

For the first apply, the function is created with an image tag pushed by hand (`make build` and `docker push` with your SSO profile). From then on, only the app pipeline deploys.

**Done when:** `curl https://<api-id>.execute-api.eu-central-1.amazonaws.com/dev/health` returns `200`, and repeated fast requests eventually return `403` from the WAF rate rule.

### Step 9. Bukvitsa service (`asternavium-infra`, `asternavium`)

1. Create `modules/bukvitsa`: its Lambda function with a `live` alias and `ignore_changes` on the image, a log group, and an endpoint the API can reach (a Lambda Function URL with `AWS_IAM` auth, if IAM is chosen in section 3).
2. Allow only the API's execution role to invoke it.
3. In the app, switch `bukvitsa_client` to SigV4-signed requests when running in AWS; the local service key stays for local runs.

**Done when:** a Bukvitsa question in `dev` chat returns a sourced answer, and an unsigned request to the Bukvitsa endpoint is rejected.

### Step 10. Deploy pipelines (`asternavium`, `asternavium-bukvitsa`)

1. Create GitHub environment `dev` in each repository with variables `AWS_REGION=eu-central-1`, `AWS_DEPLOY_ROLE_ARN`, `ECR_REPOSITORY`, `LAMBDA_FUNCTION` and, for the API, `API_BASE_URL`. No secrets are needed.
2. Add `deploy.yml`, triggered on push to `main` after CI passes:
   1. assume the repository's deploy role through OIDC;
   2. build the `arm64` image on an `ubuntu-24.04-arm` runner with the commit SHA as build argument, and push it, tagged with the full commit SHA;
   3. `update-function-code` with the new image; wait until the update completes;
   4. publish a version and move the `live` alias to it;
   5. smoke test: for the API, `GET /health` returns `200` and `GET /v1/about` returns this commit's SHA; for Bukvitsa, a known entry is returned through the API;
   6. if the smoke test fails, move the alias back to the previous version and fail the job.
3. Use a concurrency group so deploys run one at a time, in order.
4. Document rollback in each README: re-run the deploy of an older commit, or move the alias by hand.

**Done when:** a merge to `main` is live in `dev` within minutes, the smoke test is green, and a deliberately broken commit is rolled back automatically.

### Step 11. Hosted Gradio client (`asternavium-infra`, `asternavium`)

1. One-day spike on Lambda: the Gradio image behind a Function URL with response streaming and reserved concurrency of 1.
2. If streaming or session state misbehaves, fall back to Fargate with 0.25 vCPU and 1 GB, on a schedule that stops it outside working hours.
3. Either way, `dev` only, calling the `dev` API with the dev identity until Phase 5.

**Done when:** the hosted Gradio client holds a chat with the `dev` API.

### Step 12. Retire the personal AWS account from the project

1. Point all local configuration at the `dev` account through the SSO profile, or keep running locally against moto-backed fakes where that is enough.
2. Delete the `asternavium-local-*` tables in the personal account.
3. Remove the personal profile from project configuration and documentation.

**Done when:** nothing in either repository or in local `.env` files refers to the personal account, and its project tables are gone.

### Step 13. Phase close

1. Run the exit checks in section 1 end to end from a fresh commit, including a CloudWatch Logs Insights query that finds a chat request by its `request_id`.
2. Update the READMEs: architecture overview, deploy flow, rollback, how to reach the `dev` API and the Gradio client, and how to find logs in CloudWatch.
3. Record anything decided during the phase in the specification or in the infra README.

## 5. Order and effort

Rough effort for one developer; AWS onboarding usually takes longer than expected.

| Step | Repository | Depends on | Effort |
| --- | --- | --- | --- |
| 1. AWS accounts and access | – | – | 0.5 day |
| 2. Bootstrap and OIDC roles | infra | 1 | 1 day |
| 3. Infra pipeline | infra | 2 | 1 day |
| 4. ECR repositories | infra | 3 | 0.5 day |
| 5. Container images | app, Bukvitsa | – (can start in parallel with 1–4) | 1.5 days |
| 6. Logging for CloudWatch | app | – (can start in parallel with 1–4) | 0.5 day |
| 7. Data and secrets | infra, app | 3 | 1 day |
| 8. API: Lambda, API Gateway, WAF | infra | 4, 5, 7 | 1.5 days |
| 9. Bukvitsa service | infra, app | 8 | 1 day |
| 10. Deploy pipelines | app, Bukvitsa | 2, 8, 9 | 1.5 days |
| 11. Hosted Gradio client | infra, app | 10 | 1 day |
| 12. Retire the personal account | – | 10 | 0.5 day |
| 13. Phase close | all | all | 0.5 day |

Total: about 11–12 working days.

## 6. Risks

| Risk | Mitigation |
| --- | --- |
| Lambda creation fails because no image exists yet | ECR first (step 4) and one manual first push per function |
| Local table script and Terraform `data` module drift apart | Table names from settings; step 7 checks the definitions match and leaves one authoritative definition |
| Bedrock models used locally are not enabled, or behave differently, in the `dev` account | Enable the same model IDs in step 1; the model ID comes from settings, so it is one value per environment |
| OIDC trust policy too broad, so another repository or branch could assume a role | Condition on `sub` with the exact repository and environment; test that a pull request cannot assume a deploy role |
| Account ID or other account data committed to a public repository | Role ARNs and outputs live only in GitHub environment variables; Trivy and secret scanning in CI |
| Image built for the wrong architecture, or Swiss Ephemeris fails to compile | Build with `--platform linux/arm64` everywhere and in CI on pull requests; the smoke test catches a failed start |
| Problems hard to diagnose without tracing until Phase 6 | Request IDs in every log line and response, commit SHA in logs, Logs Insights queries documented in the README |
| Image size grows with LangChain and the ephemeris library | Slim base image, `--no-dev` install, `.dockerignore`; check the size in CI |

## 7. Out of scope for Phase 4

- Anything in `prod`: account, environment, release pipeline and approval gate (Phase 8)
- Datadog: account, Lambda extension, `ddtrace`, dashboard and custom metrics (Phase 6)
- Cognito and removal of the dev identity (Phase 5)
- Custom domain and ACM certificate (Phase 8, unless decided otherwise in section 3)
- Monitors and alerting (Phase 8)
- Licence scan and `NOTICE` generation in CI (before the public launch, section 14 of the specification)
