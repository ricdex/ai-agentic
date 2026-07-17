import dataclasses
import hashlib
import hmac
import json
import logging
import os
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from shared.github_client import GitHubClient
from shared.models import Issue, Task, TaskStatus
from shared.queue_client import QUEUE_IMPLEMENT, QUEUE_SPEC_PENDING, QueueClient
from triage_agent import generate_spec, triage_issue

logging.basicConfig(level=logging.INFO, format="%(asctime)s [orchestrator] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Factory Orchestrator")
queue = QueueClient()
github = GitHubClient()

WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]


def verify_signature(payload: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def process_issue(issue: Issue) -> None:
    logger.info(f"Issue #{issue.number}: {issue.title}")

    triage = triage_issue(issue.title, issue.body, issue.repo)
    logger.info(
        f"Triage → automatable={triage.automatable}, "
        f"complexity={triage.complexity}, needs_spec={triage.needs_spec}"
    )

    if not triage.automatable:
        github.post_comment(
            issue.repo, issue.number,
            f"🤖 **Factory Triage** — Issue no automatable.\n\n"
            f"**Razón:** {triage.reasoning}\n\n"
            f"Requiere intervención manual.",
        )
        github.add_label(issue.repo, issue.number, ["factory:manual"])
        return

    task_id = str(uuid.uuid4())[:8]
    branch_name = f"factory/{task_id}/issue-{issue.number}"
    github.add_label(issue.repo, issue.number, [f"factory:{triage.complexity.value}"])

    task = Task(
        id=task_id,
        issue=issue,
        triage=triage,
        status=TaskStatus.TRIAGED,
        branch_name=branch_name,
    )

    if triage.needs_spec:
        spec = generate_spec(issue.title, issue.body, triage.suggested_approach)
        task.spec = spec
        task.status = TaskStatus.SPEC_PENDING

        github.post_comment(
            issue.repo, issue.number,
            f"## 🏭 Factory — Spec generado\n\n"
            f"{spec}\n\n"
            f"---\n"
            f"Responde con `/factory approve` para iniciar implementación, "
            f"o `/factory reject <feedback>` para pedir cambios.\n\n"
            f"*Task ID: `{task_id}`*",
        )
        queue.push(QUEUE_SPEC_PENDING, {
            "task": dataclasses.asdict(task),
            "issue_number": issue.number,
            "repo": issue.repo,
        })
        logger.info(f"Task {task_id} waiting for spec approval")
    else:
        task.status = TaskStatus.IMPLEMENTING
        github.post_comment(
            issue.repo, issue.number,
            f"🏭 **Factory** — Implementación iniciada.\n\n"
            f"**Enfoque:** {triage.suggested_approach}\n"
            f"**Complejidad:** {triage.complexity.value}\n"
            f"**Branch:** `{branch_name}`\n\n"
            f"*Task ID: `{task_id}`*",
        )
        queue.push(QUEUE_IMPLEMENT, dataclasses.asdict(task))
        logger.info(f"Task {task_id} queued for implementation")


@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")

    if not verify_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = request.headers.get("x-github-event", "")
    data = json.loads(payload)

    if event != "issues" or data.get("action") != "opened":
        return {"status": "ignored", "event": event, "action": data.get("action")}

    raw = data["issue"]
    issue = Issue(
        number=raw["number"],
        title=raw["title"],
        body=raw.get("body") or "",
        repo=data["repository"]["full_name"],
        labels=[l["name"] for l in raw.get("labels", [])],
    )

    background_tasks.add_task(process_issue, issue)
    return {"status": "accepted", "issue": issue.number}


@app.get("/health")
def health():
    return {"status": "ok", "service": "orchestrator"}
