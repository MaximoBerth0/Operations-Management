# Deployment

The API ships as a single container image and runs on **AWS ECS (Fargate)** behind an **Application Load Balancer**, backed by **Amazon RDS for PostgreSQL**. This page is the architectural overview; the copy-paste runbook (ECR push, `register-task-definition`, `create-service`, autoscaling) lives in [deploy/README.md](../deploy/README.md), with the task definition in [deploy/ecs-task-definition.json](../deploy/ecs-task-definition.json).

## Stack overview

```
                      Route 53 (DNS)
                         │  api.yourdomain.com
                         ▼
Internet ──► Application Load Balancer (HTTPS :443, ACM cert)
                 │   health check: GET /health
                 ▼
           ECS Service (Fargate, desired-count ≥ 2)
           └─ Task: api container :8000  (private subnets, no public IP)
                ├─ on start: alembic upgrade head → gunicorn (uvicorn workers)
                ├─ Secrets Manager ──► config JSON bundle (fetched by the app)
                ├─ Task IAM role   ──► GetSecretValue + SES SendEmail
                └─ CloudWatch Logs ──► /ecs/management-api
                         │
                         ▼
                 Amazon RDS (PostgreSQL, private, TLS required)
```

## Image

Multi-stage [Dockerfile](../docker/Dockerfile): a builder stage installs locked runtime deps into a venv with Poetry; the runtime stage copies only that venv onto a slim Python base, runs as a **non-root** user, and uses **tini** as PID 1. [entrypoint.sh](../docker/entrypoint.sh) runs `alembic upgrade head` (unless `RUN_MIGRATIONS=false`) and then execs **gunicorn** with uvicorn workers on `0.0.0.0:8000`.

## Compute — ECS Fargate + ALB

- The image is pushed to **ECR** (`management-api`), referenced by the task definition.
- The **ECS service** runs ≥ 2 tasks in **private subnets** with `assignPublicIp=DISABLED`; only the ALB is internet-facing.
- The **ALB** terminates HTTPS on :443 (ACM certificate) and forwards to container port 8000. Its target-group health check hits `/health` (liveness, no DB). `/health/ready` additionally verifies the database if you want a deeper probe.
- **Auto scaling** is target-tracking on CPU (≈60%), min 2 / max 10 tasks.
- **Migrations** run on task start and are idempotent, so a rolling deploy with multiple tasks is safe. **Seeding** roles/permissions is a separate one-off `run-task` with `RUN_MIGRATIONS=false`.

## Database — RDS PostgreSQL

Managed PostgreSQL on RDS, reachable only from the ECS task's security group (private). The connection string comes from the secret bundle as `DATABASE_URL` (asyncpg driver). TLS is **required** by the app — RDS is never reached in plaintext (see [database_design](database_design.md) for pooling and timeout tuning).

## Secret management

There is **no `.env` in the image**. At startup the app reads a single JSON object from **AWS Secrets Manager** (named by `AWS_SECRETS_NAME`, e.g. `management/prod`) and maps its keys onto its settings — `DATABASE_URL`, `SECRET_KEY`, `SENDER_EMAIL`, `APP_BASE_URL`, `CORS_ALLOW_ORIGINS`, etc. ([secrets.py](../app/core/secrets.py)).

Settings precedence (highest first): **explicit env vars → Secrets Manager bundle → local `.env` → file secrets**. So ECS-injected env vars can patch a single value on one task without editing the shared secret. In prod the app loudly refuses to start if the secret is missing or malformed.

**No static credentials.** Both Secrets Manager and SES resolve through boto3's default credential chain, which on Fargate is the **task IAM role**. Two roles are involved:

- **Execution role** — lets ECS pull the image from ECR and write to CloudWatch Logs.
- **Task role** — `secretsmanager:GetSecretValue` on the config secret **plus** `ses:SendEmail` / `ses:SendRawEmail` for outbound mail (password-reset emails).

## DNS resolution

**Route 53** hosts the public zone. An alias record (e.g. `api.yourdomain.com`) points at the ALB; the ALB's HTTPS listener uses an **ACM** certificate for that name. Clients resolve the hostname to the ALB, which routes to healthy ECS tasks. `APP_BASE_URL` (in the secret bundle) must match this public URL, since it's embedded in the links sent in password-reset emails.

## Observability

- **Logs** — gunicorn access/error logs stream to stdout and are shipped to **CloudWatch Logs** (`/ecs/management-api`). Each request carries a request id (see `app/observability/`).
- **Health** — the container-level `HEALTHCHECK` and the ECS/ALB health checks both probe `/health`.
