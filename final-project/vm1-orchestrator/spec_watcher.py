"""
Polls GitHub for /factory approve or /factory reject on spec-pending issues.
Runs as a separate process alongside the FastAPI server.
"""
import logging
import os
import time

from shared.github_client import GitHubClient
from shared.models import TaskStatus
from shared.queue_client import QUEUE_IMPLEMENT, QUEUE_SPEC_PENDING, QueueClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [spec-watcher] %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 30  # seconds


def check_approval(github: GitHubClient, repo: str, issue_number: int) -> tuple[bool | None, str]:
    """Returns (True=approved, False=rejected, None=no decision yet), feedback"""
    comments = github.get_comments(repo, issue_number)
    for comment in reversed(comments):
        body = comment["body"].strip()
        if body.startswith("/factory approve"):
            return True, ""
        if body.startswith("/factory reject"):
            feedback = body.replace("/factory reject", "").strip()
            return False, feedback
    return None, ""


def run():
    queue = QueueClient()
    github = GitHubClient()
    pending: dict[str, dict] = {}

    logger.info("Spec watcher started")

    while True:
        # Drain spec-pending queue into local dict
        while True:
            item = queue.pop(QUEUE_SPEC_PENDING, timeout=0)
            if not item:
                break
            task_id = item["task"]["id"]
            pending[task_id] = item
            logger.info(f"Watching spec for task {task_id} (issue #{item['issue_number']})")

        # Check each pending task
        for task_id, item in list(pending.items()):
            repo = item["repo"]
            issue_number = item["issue_number"]
            task_data = item["task"]

            decision, feedback = check_approval(github, repo, issue_number)

            if decision is True:
                logger.info(f"Task {task_id} approved → queuing for implementation")
                task_data["status"] = TaskStatus.IMPLEMENTING.value
                queue.push(QUEUE_IMPLEMENT, task_data)
                github.post_comment(
                    repo, issue_number,
                    f"✅ Spec aprobado. Iniciando implementación.\n\n*Task ID: `{task_id}`*",
                )
                del pending[task_id]

            elif decision is False:
                logger.info(f"Task {task_id} rejected: {feedback}")
                github.post_comment(
                    repo, issue_number,
                    f"❌ Spec rechazado.\n\n**Feedback:** {feedback}\n\n"
                    f"El issue queda para revisión manual.",
                )
                del pending[task_id]

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
