"""
Módulo 11 — Lambda Handler de producción

Handler para AWS Lambda que recibe webhooks de GitHub,
valida la firma HMAC, y encola el issue en SQS para
procesamiento asíncrono por el agent worker.

Deploy:
    zip -r webhook.zip lambda_handler.py
    aws lambda update-function-code --function-name autopilot-webhook --zip-file fileb://webhook.zip

Variables de entorno requeridas en Lambda:
    ISSUE_QUEUE_URL          → URL de la SQS queue
    GITHUB_WEBHOOK_SECRET    → Secret del webhook de GitHub (desde Secrets Manager)
"""

import json
import os
import hmac
import hashlib
import logging
import uuid
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client("sqs")

ISSUE_QUEUE_URL = os.environ["ISSUE_QUEUE_URL"]
WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]
SUPPORTED_ACTIONS = {"opened", "labeled", "reopened"}


def lambda_handler(event: dict, context) -> dict:
    trace_id = str(uuid.uuid4())[:8]
    logger.info(json.dumps({"trace_id": trace_id, "event": "webhook_received"}))

    try:
        return _process(event, trace_id)
    except Exception as e:
        logger.error(json.dumps({
            "trace_id": trace_id,
            "event": "unhandled_error",
            "error": str(e)
        }))
        return _response(500, {"error": "Internal error"})


def _process(event: dict, trace_id: str) -> dict:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = event.get("body") or ""

    # 1. Validar firma HMAC-SHA256
    signature = headers.get("x-hub-signature-256", "")
    if not _verify_signature(body, signature):
        logger.warning(json.dumps({"trace_id": trace_id, "event": "invalid_signature"}))
        return _response(401, {"error": "Invalid signature"})

    # 2. Parsear payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON"})

    event_type = headers.get("x-github-event", "")
    action = payload.get("action", "")

    # 3. Filtrar solo events relevantes
    if event_type != "issues" or action not in SUPPORTED_ACTIONS:
        logger.info(json.dumps({
            "trace_id": trace_id,
            "event": "ignored",
            "github_event": event_type,
            "action": action
        }))
        return _response(200, {"status": "ignored"})

    # 4. Encolar para procesamiento asíncrono
    issue = payload.get("issue", {})
    repo = payload.get("repository", {})

    job = {
        "trace_id": trace_id,
        "issue_number": issue.get("number"),
        "title": issue.get("title", ""),
        "body": issue.get("body", ""),
        "repo_full_name": repo.get("full_name", ""),
        "repo_clone_url": repo.get("clone_url", ""),
        "action": action
    }

    sqs.send_message(
        QueueUrl=ISSUE_QUEUE_URL,
        MessageBody=json.dumps(job),
        MessageGroupId=str(issue.get("number")),  # para FIFO queue: un issue a la vez
        MessageDeduplicationId=f"{issue.get('number')}-{action}"
    )

    logger.info(json.dumps({
        "trace_id": trace_id,
        "event": "issue_queued",
        "issue_number": issue.get("number"),
        "repo": repo.get("full_name")
    }))

    return _response(202, {"status": "queued", "trace_id": trace_id})


def _verify_signature(body: str, signature: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }
