import dataclasses
import logging

from shared.github_client import GitHubClient
from shared.models import TaskStatus
from shared.queue_client import QUEUE_IMPLEMENT, QUEUE_REVIEW, QueueClient
from implementation_agent import implement
from sandbox import Sandbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s [implementor] %(message)s")
logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def process_task(raw: dict) -> None:
    queue = QueueClient()
    github = GitHubClient()

    task_id = raw["id"]
    issue = raw["issue"]
    branch_name = raw["branch_name"]
    spec = raw.get("spec", "")
    retries = raw.get("retries", 0)
    repo = issue["repo"]
    issue_number = issue["number"]

    attempt = retries + 1
    logger.info(f"Task {task_id} — attempt {attempt}/{MAX_RETRIES}")

    github.post_comment(
        repo, issue_number,
        f"🔧 **Implementando** (intento {attempt}/{MAX_RETRIES})…",
    )

    try:
        with Sandbox(repo, branch_name) as sandbox:
            result = implement(
                issue_title=issue["title"],
                issue_body=issue["body"],
                spec=spec,
                sandbox=sandbox,
                use_powerful=(retries >= MAX_RETRIES - 1),
            )

        if result["success"]:
            if sandbox.commit_and_push(
                f"fix: {issue['title']} (closes #{issue_number})\n\n{result['summary']}"
            ):
                raw["status"] = TaskStatus.REVIEWING.value
                raw["impl_result"] = result
                queue.push(QUEUE_REVIEW, raw)
                logger.info(f"Task {task_id} → review queue")

                github.post_comment(
                    repo, issue_number,
                    f"✅ **Implementación lista.** Enviando a revisión automática.\n\n"
                    f"**Branch:** `{branch_name}`\n"
                    f"**Tests:** ✓ passing\n\n"
                    f"```\n{result['summary']}\n```",
                )
            else:
                raise RuntimeError("git push failed")

        else:
            retries += 1
            if retries < MAX_RETRIES:
                logger.warning(f"Tests failed — retry {retries}/{MAX_RETRIES}")
                raw["retries"] = retries
                queue.push(QUEUE_IMPLEMENT, raw)
            else:
                github.post_comment(
                    repo, issue_number,
                    f"❌ **Factory falló** tras {MAX_RETRIES} intentos.\n\n"
                    f"**Último error:**\n```\n{result['test_output'][:500]}\n```\n\n"
                    f"Requiere intervención manual.",
                )
                github.add_label(repo, issue_number, ["factory:failed"])

    except Exception as e:
        logger.exception(f"Task {task_id} crashed: {e}")
        github.post_comment(
            repo, issue_number,
            f"❌ **Error en factory:**\n```\n{str(e)[:300]}\n```",
        )


def run():
    queue = QueueClient()
    logger.info("Implementor worker started — waiting for tasks")

    while True:
        item = queue.pop(QUEUE_IMPLEMENT, timeout=30)
        if item:
            process_task(item)


if __name__ == "__main__":
    run()
