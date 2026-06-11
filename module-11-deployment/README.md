# Módulo 11 — Deployment: Agentes en Producción

> "Un agente que corre en tu laptop no es un agente de producción. Es un prototipo."

---

## 11.1 El gap entre demo y producción

Un agente funciona en local. ¿Qué falta para que funcione en producción?

```
Demo local:
  - Corre en tu máquina
  - Sin limits de concurrencia
  - Sin manejo de fallos del runtime
  - Sin monitoreo
  - Sin autoscaling
  - Sin secrets management

Producción:
  ✓ Infraestructura reproducible (IaC)
  ✓ Timeouts y limits explícitos
  ✓ Secrets en secret manager, no en .env
  ✓ Logs estructurados con trace_id
  ✓ Health checks
  ✓ Rollback automático
  ✓ Alertas en caso de error
```

---

## 11.2 Dos patrones de deployment para agentes

### Patrón A: Serverless (FaaS) — para tareas cortas

Cuándo usarlo: respuestas en < 15 minutos, sin estado entre ejecuciones.

```
GitHub Webhook → API Gateway → Lambda → [agente] → GitHub API
```

Ventajas:
- Costo cero cuando no se usa
- Autoscaling automático
- Sin gestión de servidores

Limitación: timeout máximo de 15 minutos en Lambda, sin estado persistente.

### Patrón B: Container con worker (ECS / Cloud Run) — para tareas largas

Cuándo usarlo: agentes que corren por horas, necesitan estado, o procesan en batch.

```
Redis Queue → [ECS Worker] → [agente de larga duración] → resultados
```

Ventajas:
- Sin límite de tiempo
- Puede mantener estado en memoria
- Mejor para workloads predecibles

Limitación: costo fijo aunque no haya trabajo, más complejidad operativa.

---

## 11.3 Containerizar el agente

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/

# Usuario no-root para seguridad
RUN useradd -m -u 1001 agentuser
USER agentuser

CMD ["python", "-m", "agent.worker"]
```

**Variables de entorno vs secretos:**

```python
# ❌ Nunca en el código ni en .env commiteado
ANTHROPIC_API_KEY = "sk-ant-..."

# ✓ Secretos en AWS Secrets Manager / GCP Secret Manager
import boto3
secret = boto3.client("secretsmanager").get_secret_value(SecretId="prod/anthropic-key")
api_key = json.loads(secret["SecretString"])["key"]

# ✓ O via variable de entorno inyectada por el runtime (ECS task definition, Cloud Run)
api_key = os.environ["ANTHROPIC_API_KEY"]  # el runtime la inyecta desde el secret manager
```

---

## 11.4 Lambda para el webhook handler

```python
# handler.py
import json
import os
import boto3
import hmac
import hashlib

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["ISSUE_QUEUE_URL"]
WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]


def lambda_handler(event, context):
    body = event.get("body", "")
    signature = event.get("headers", {}).get("x-hub-signature-256", "")

    # Validar firma HMAC
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return {"statusCode": 401, "body": "Invalid signature"}

    payload = json.loads(body)
    if payload.get("action") not in ("opened", "labeled"):
        return {"statusCode": 200, "body": "Ignored"}

    # Encolar para procesamiento asíncrono
    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "issue_number": payload["issue"]["number"],
            "title": payload["issue"]["title"],
            "body": payload["issue"]["body"],
            "repo": payload["repository"]["full_name"]
        })
    )

    return {"statusCode": 202, "body": "Queued"}
```

---

## 11.5 Health checks

Todo servicio en producción necesita un endpoint de health:

```python
# Para el agent worker (FastAPI)
@app.get("/health")
async def health():
    checks = {
        "redis": check_redis(),
        "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
        "queue_depth": get_queue_depth()
    }
    all_ok = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ok" if all_ok else "degraded", "checks": checks}
    )
```

---

## 11.6 IaC mínima (Terraform)

```hcl
# main.tf — infraestructura mínima para el proyecto Autopilot

resource "aws_lambda_function" "webhook_handler" {
  filename      = "webhook.zip"
  function_name = "autopilot-webhook"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 30

  environment {
    variables = {
      ISSUE_QUEUE_URL      = aws_sqs_queue.issues.url
      GITHUB_WEBHOOK_SECRET = data.aws_secretsmanager_secret_version.webhook_secret.secret_string
    }
  }
}

resource "aws_sqs_queue" "issues" {
  name                       = "autopilot-issues"
  visibility_timeout_seconds = 900  # 15 min para que el agente procese
  message_retention_seconds  = 86400  # 1 día
}

resource "aws_ecs_service" "agent_worker" {
  name            = "autopilot-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.agent.arn
  desired_count   = 1

  # Autoscaling basado en profundidad de la cola
  # Ver: aws_appautoscaling_policy más abajo
}
```

---

## 11.7 Checklist de deployment

Antes de poner el agente en producción real:

- [ ] Dockerfile con usuario no-root
- [ ] Secrets en secret manager (no en .env ni código)
- [ ] Timeout explícito en todas las herramientas del agente
- [ ] Health check endpoint
- [ ] Logs estructurados con trace_id (no `print()`)
- [ ] Alertas: error rate > 5%, cost > umbral diario
- [ ] Limit de gasto en Anthropic Console
- [ ] Rollback plan: ¿cómo deshabilitar el agente en 1 minuto?
- [ ] Runbook: ¿qué hace el on-call si el agente se cuelga?

---

## Ejemplos de código

- [`lambda_handler.py`](./examples/lambda_handler.py) — Handler Lambda completo con validación HMAC y SQS
- [`Dockerfile`](./examples/Dockerfile) — Container para el agent worker
- [`cloudrun.yaml`](./examples/cloudrun.yaml) — Deploy en Google Cloud Run
- [`terraform/`](./examples/terraform/) — IaC mínima para AWS

---

## Ejercicio

Desplegá el proyecto Autopilot en algún cloud (AWS, GCP, o Railway para empezar):

1. Containerizá el agent-core con el Dockerfile del ejemplo
2. Subilo a un container registry (ECR, GCR, o Docker Hub)
3. Deployá el webhook handler en Lambda o Cloud Run
4. Configurá un webhook real en un repo de prueba en GitHub
5. Abrí un issue y observá el pipeline completo funcionando

Cuando funcione de punta a punta, tenés un sistema agéntico en producción real.

---

**Fin del curso avanzado.**

Recorriste:
- Módulo 6: RAG y memoria semántica
- Módulo 7: Structured outputs confiables
- Módulo 8: MCP — el protocolo estándar
- Módulo 9: Streaming para UX en producción
- Módulo 10: Evals para mejorar sin adivinar
- Módulo 11: Deployment real, no demos
