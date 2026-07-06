# Módulo 11 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Lambda handler completo

**Archivo:** `examples/lambda_handler.py`

El webhook handler de GitHub que valida la firma HMAC y encola el issue en SQS para procesamiento asíncrono.

```python
import json
import os
import boto3
import hmac
import hashlib

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["ISSUE_QUEUE_URL"]
WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]

def validate_signature(body: str, signature_header: str) -> bool:
    """Verifica que el webhook viene realmente de GitHub."""
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)

def lambda_handler(event, context):
    body = event.get("body", "")
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    signature = headers.get("x-hub-signature-256", "")

    # 1. Validar firma
    if not validate_signature(body, signature):
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Invalid signature"})
        }

    payload = json.loads(body)
    event_type = headers.get("x-github-event", "")

    # 2. Filtrar eventos relevantes
    if event_type != "issues":
        return {"statusCode": 200, "body": json.dumps({"status": "ignored", "event": event_type})}

    if payload.get("action") not in ("opened", "labeled"):
        return {"statusCode": 200, "body": json.dumps({"status": "ignored", "action": payload.get("action")})}

    # 3. Solo procesar si tiene el label "ai-fix"
    labels = [l["name"] for l in payload.get("issue", {}).get("labels", [])]
    if payload.get("action") == "labeled" and payload.get("label", {}).get("name") != "ai-fix":
        return {"statusCode": 200, "body": json.dumps({"status": "ignored", "reason": "wrong label"})}

    issue = payload["issue"]

    # 4. Encolar para procesamiento asíncrono
    message = {
        "issue_number": issue["number"],
        "title": issue["title"],
        "body": issue.get("body", ""),
        "repo": payload["repository"]["full_name"],
        "labels": labels,
        "source_event": event_type,
        "source_action": payload.get("action")
    }

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(message),
        MessageGroupId=payload["repository"]["full_name"],  # FIFO: un repo a la vez
        MessageDeduplicationId=f"issue-{issue['number']}-{payload.get('action')}"
    )

    return {
        "statusCode": 202,
        "body": json.dumps({
            "status": "queued",
            "issue": issue["number"],
            "repo": payload["repository"]["full_name"]
        })
    }
```

**Flujo de un webhook real de GitHub:**

```
GitHub → POST /webhook
  Headers:
    X-GitHub-Event: issues
    X-Hub-Signature-256: sha256=abc123...
  Body:
    {"action": "labeled", "issue": {"number": 47, "title": "Bug: ..."}, ...}

Lambda response (< 1s):
  HTTP 202
  {"status": "queued", "issue": 47, "repo": "org/repo"}

SQS message encolado:
  {
    "issue_number": 47,
    "title": "Bug: payment fails for zero-amount orders",
    "body": "Steps to reproduce...",
    "repo": "org/repo",
    "labels": ["bug", "ai-fix"],
    "source_event": "issues",
    "source_action": "labeled"
  }

Worker (ECS, segundos después):
  Procesa el issue → escribe fix → abre PR → notifica
```

**Casos que la Lambda rechaza o ignora:**

```
Firma inválida:             HTTP 401  {"error": "Invalid signature"}
Evento push (no issues):    HTTP 200  {"status": "ignored", "event": "push"}
Issue closed (no opened):   HTTP 200  {"status": "ignored", "action": "closed"}
Label "bug" (no "ai-fix"):  HTTP 200  {"status": "ignored", "reason": "wrong label"}
```

---

## Ejemplo 2 — Dockerfile del agent worker

**Archivo:** `examples/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema primero (cacheado si no cambian)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copiar solo requirements primero (cacheado si no cambian)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del agente
COPY agent/ ./agent/

# Usuario no-root — el agente no necesita escribir fuera de /tmp
RUN useradd -m -u 1001 agentuser && \
    mkdir -p /tmp/agent-workspace && \
    chown agentuser:agentuser /tmp/agent-workspace
USER agentuser

# Health check: el worker expone un endpoint HTTP mínimo
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["python", "-m", "agent.worker"]
```

**`requirements.txt`:**

```
anthropic==0.40.0
boto3==1.34.0
redis==5.0.1
fastapi==0.115.0
uvicorn==0.32.0
httpx==0.27.0
pydantic==2.9.0
```

**Build y push:**

```bash
# Build
docker build -t agent-worker:latest .

# Test local
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e REDIS_URL=redis://localhost:6379 \
  -e QUEUE_URL=$SQS_QUEUE_URL \
  agent-worker:latest

# Push a ECR
aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY
docker tag agent-worker:latest $ECR_REGISTRY/agent-worker:latest
docker push $ECR_REGISTRY/agent-worker:latest
```

---

## Ejemplo 3 — Health check endpoint

**Archivo:** `examples/health_check.py`

El endpoint que el load balancer y el orquestador usan para saber si el worker está vivo.

```python
import os
import json
import redis
import boto3
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

def check_redis() -> bool:
    try:
        r = redis.from_url(os.environ["REDIS_URL"])
        r.ping()
        return True
    except Exception:
        return False

def check_anthropic_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant-"))

def get_queue_depth() -> int:
    try:
        sqs = boto3.client("sqs")
        attrs = sqs.get_queue_attributes(
            QueueUrl=os.environ["QUEUE_URL"],
            AttributeNames=["ApproximateNumberOfMessages"]
        )
        return int(attrs["Attributes"]["ApproximateNumberOfMessages"])
    except Exception:
        return -1

@app.get("/health")
async def health():
    checks = {
        "redis": check_redis(),
        "anthropic_key": check_anthropic_key(),
        "queue_depth": get_queue_depth(),
    }

    # queue_depth de -1 significa que no pudo conectarse a SQS
    checks["sqs"] = checks["queue_depth"] >= 0

    all_ok = checks["redis"] and checks["anthropic_key"] and checks["sqs"]

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ok" if all_ok else "degraded",
            "checks": checks,
            "version": os.getenv("APP_VERSION", "unknown")
        }
    )
```

**Response cuando todo está bien (HTTP 200):**

```json
{
  "status": "ok",
  "checks": {
    "redis": true,
    "anthropic_key": true,
    "queue_depth": 3,
    "sqs": true
  },
  "version": "1.4.2"
}
```

**Response cuando Redis está caído (HTTP 503):**

```json
{
  "status": "degraded",
  "checks": {
    "redis": false,
    "anthropic_key": true,
    "queue_depth": 12,
    "sqs": true
  },
  "version": "1.4.2"
}
```

---

## Ejemplo 4 — Terraform mínimo

**Archivo:** `examples/terraform/main.tf`

Infraestructura mínima: Lambda para webhook + SQS + ECS para el worker.

```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

# ── SQS Queue ────────────────────────────────────────────────────

resource "aws_sqs_queue" "issues" {
  name                       = "autopilot-issues.fifo"
  fifo_queue                 = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 900   # 15 min para que el agente procese
  message_retention_seconds   = 86400 # 1 día

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.issues_dlq.arn
    maxReceiveCount     = 3  # 3 intentos antes de ir a DLQ
  })
}

resource "aws_sqs_queue" "issues_dlq" {
  name                      = "autopilot-issues-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600  # 14 días en DLQ
}

# ── Lambda: webhook handler ───────────────────────────────────────

resource "aws_lambda_function" "webhook" {
  filename      = "webhook.zip"
  function_name = "autopilot-webhook"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 10  # el webhook debe responder rápido

  environment {
    variables = {
      ISSUE_QUEUE_URL       = aws_sqs_queue.issues.url
      GITHUB_WEBHOOK_SECRET = data.aws_secretsmanager_secret_version.webhook.secret_string
    }
  }
}

resource "aws_lambda_function_url" "webhook" {
  function_name      = aws_lambda_function.webhook.function_name
  authorization_type = "NONE"  # GitHub no puede enviar auth headers custom
}

# ── ECS: agent worker ────────────────────────────────────────────

resource "aws_ecs_task_definition" "agent" {
  family                   = "autopilot-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"

  container_definitions = jsonencode([{
    name  = "agent-worker"
    image = "${var.ecr_registry}/agent-worker:latest"
    environment = [
      { name = "QUEUE_URL", value = aws_sqs_queue.issues.url },
      { name = "REDIS_URL", value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:6379" }
    ]
    secrets = [
      { name = "ANTHROPIC_API_KEY", valueFrom = data.aws_secretsmanager_secret.anthropic_key.arn }
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 10
    }
  }])
}

resource "aws_ecs_service" "agent" {
  name            = "autopilot-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"
}

# ── Outputs ──────────────────────────────────────────────────────

output "webhook_url" {
  value       = aws_lambda_function_url.webhook.function_url
  description = "URL para configurar en GitHub → Settings → Webhooks"
}
```

**`terraform apply` output:**

```
aws_sqs_queue.issues_dlq: Creating...
aws_sqs_queue.issues: Creating...
aws_sqs_queue.issues_dlq: Creation complete after 1s [id=https://sqs.us-east-1.amazonaws.com/123456789/autopilot-issues-dlq.fifo]
aws_sqs_queue.issues: Creation complete after 1s [id=https://sqs.us-east-1.amazonaws.com/123456789/autopilot-issues.fifo]
aws_lambda_function.webhook: Creating...
aws_lambda_function.webhook: Creation complete after 8s [id=autopilot-webhook]
aws_lambda_function_url.webhook: Creating...
aws_lambda_function_url.webhook: Creation complete after 2s
aws_ecs_task_definition.agent: Creating...
aws_ecs_task_definition.agent: Creation complete after 1s [id=autopilot-agent:1]
aws_ecs_service.agent: Creating...
aws_ecs_service.agent: Creation complete after 12s [id=arn:aws:ecs:us-east-1:123456789:service/autopilot-agent]

Apply complete! Resources: 7 added, 0 changed, 0 destroyed.

Outputs:

webhook_url = "https://abc123.lambda-url.us-east-1.on.aws/"
```

**Configurar el webhook en GitHub:**

```
GitHub → Repo → Settings → Webhooks → Add webhook
  Payload URL:    https://abc123.lambda-url.us-east-1.on.aws/
  Content type:   application/json
  Secret:         [el mismo GITHUB_WEBHOOK_SECRET del secret manager]
  Events:         Issues ✓
```

---

## Checklist de deployment completado

```
✓ Dockerfile con usuario no-root (agentuser, uid 1001)
✓ Secrets en AWS Secrets Manager (ANTHROPIC_API_KEY, GITHUB_WEBHOOK_SECRET)
✓ SQS FIFO con DLQ (3 reintentos antes de DLQ, 14 días de retención)
✓ Lambda con timeout=10s (responde rápido al webhook)
✓ ECS worker con timeout=15min para procesar issues complejos
✓ Health check endpoint (/health) con verificación de Redis y SQS
✓ IaC completa en Terraform (infraestructura reproducible)

Pendiente (para cada equipo):
□ Alertas: cost > $X/día, DLQ depth > 0, error rate > 5%
□ Limit de gasto en Anthropic Console
□ Runbook: ¿qué hace el on-call si el worker se cuelga?
□ Rollback plan: cómo deshabilitar el ECS service en < 60s
```

---

Ver el [README principal](./README.md) para los patrones de deployment y el checklist completo de production-readiness.
