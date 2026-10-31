# AWS Deployment

The Management API ships as a single container image and runs on **Amazon ECS
(Fargate)** behind an **Application Load Balancer**. This directory holds the
deploy artifacts; the steps below take you from a clean AWS account to a running
service.

## Architecture

```
Internet ──► ALB (HTTPS :443)
                │   health check: GET /health
                ▼
        ECS Service (Fargate)
        ├─ Task: api container :8000
        │    └─ on start: load config from Secrets Manager,
        │                 alembic upgrade head, then gunicorn
        ├─ Secrets Manager  ──► config JSON bundle (fetched by the app)
        ├─ Task IAM role    ──► GetSecretValue + SES SendEmail (no static keys)
        └─ Auto Scaling     ──► target-tracking on CPU / memory
                │
                ▼
        Amazon RDS (PostgreSQL)
```

## Prerequisites

- An ECR repository: `management-api`
- An RDS PostgreSQL instance reachable from the ECS task's security group
- A Secrets Manager secret named `management/prod` holding a **single JSON
  object** whose keys match the app's settings. The app reads this bundle itself
  at startup (via `AWS_SECRETS_NAME`), so all sensitive/config values live here:
  ```json
  {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@your-rds-host:5432/management",
    "SECRET_KEY": "a-strong-secret-at-least-32-characters-long",
    "SENDER_EMAIL": "no-reply@yourdomain.com",
    "APP_BASE_URL": "https://api.yourdomain.com",
    "CORS_ALLOW_ORIGINS": ["https://app.yourdomain.com"],
    "DEBUG": false,
    "SENTRY_DSN": "https://<key>@<org>.ingest.sentry.io/<project>"
  }
  ```
  `SENTRY_DSN` is optional: without it error reporting stays off.
- Two IAM roles:
  - **execution role** — `AmazonECSTaskExecutionRolePolicy` (lets ECS pull the
    image from ECR and write logs to CloudWatch)
  - **task role** — `secretsmanager:GetSecretValue` on the `management/prod`
    secret (the app fetches the bundle at startup) **plus** `ses:SendEmail` /
    `ses:SendRawEmail` (mail uses the task role, no static credentials)

## 1. Build and push the image to ECR

```bash
AWS_REGION=us-east-1
ACCOUNT_ID=<your-account-id>
REPO=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/management-api

aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker build -f docker/Dockerfile --build-arg GIT_SHA=$(git rev-parse HEAD) \
  -t management-api:latest .
docker tag management-api:latest $REPO:latest
docker push $REPO:latest
```

## 2. Register the task definition

Edit [`ecs-task-definition.json`](ecs-task-definition.json) and replace the
`<ACCOUNT_ID>` / `<AWS_REGION>` placeholders and confirm `AWS_SECRETS_NAME`
matches your secret name. Then:

```bash
aws ecs register-task-definition \
  --cli-input-json file://deploy/ecs-task-definition.json
```

## 3. Create / update the service

First time (wire it to your ALB target group and subnets):

```bash
aws ecs create-service \
  --cluster management \
  --service-name management-api \
  --task-definition management-api \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-aaa,subnet-bbb],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=<TG_ARN>,containerName=api,containerPort=8000" \
  --health-check-grace-period-seconds 30
```

Subsequent deploys (after pushing a new image with the same tag):

```bash
aws ecs update-service --cluster management --service management-api \
  --force-new-deployment
```

## 4. Auto scaling (target tracking)

```bash
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/management/management-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 --max-capacity 10

aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/management/management-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu-target-tracking \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration \
    '{"TargetValue":60.0,"PredefinedMetricSpecification":{"PredefinedMetricType":"ECSServiceAverageCPUUtilization"}}'
```

## Notes

- **Configuration** is pulled from Secrets Manager at startup: the app reads the
  JSON object named by `AWS_SECRETS_NAME` and maps its keys onto its settings.
  Individual env vars still override the bundle, so you can patch one value on a
  task without editing the secret. There is no `.env` in the image.
- **Migrations** run automatically on container start (`alembic upgrade head` in
  `docker/entrypoint.sh`). Alembic is idempotent, so multiple tasks starting at
  once is safe. Set `RUN_MIGRATIONS=false` on any task that must not migrate.
- **Seeding** roles/permissions is a one-off; run it as a standalone task:
  ```bash
  aws ecs run-task --cluster management --task-definition management-api \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-aaa],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
    --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","app.bootstraps.seed_all"],"environment":[{"name":"RUN_MIGRATIONS","value":"false"}]}]}'
  ```
- **ALB target group** health check path: `/health` (liveness, no DB hit).
  `/health/ready` additionally verifies the database connection if you want a
  deeper probe.
- **Credentials**: both Secrets Manager and SES resolve through boto3's default
  credential chain, which on ECS/Fargate is the task IAM role. Grant that role
  the relevant `secretsmanager:GetSecretValue` and `ses:SendEmail` permissions.
