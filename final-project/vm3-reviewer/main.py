import logging
import os
import shutil
import subprocess
import tempfile

from shared.github_client import GitHubClient
from shared.queue_client import QUEUE_REVIEW, QueueClient
from pr_creator import create_pr
from review_agent import review_code

logging.basicConfig(level=logging.INFO, format="%(asctime)s [reviewer] %(message)s")
logger = logging.getLogger(__name__)


def get_diff(repo: str, branch: str) -> str:
    workdir = tempfile.mkdtemp(prefix="factory_review_")
    try:
        repo_url = (
            f"https://x-access-token:{os.environ['GITHUB_TOKEN']}"
            f"@github.com/{repo}.git"
        )
        subprocess.run(
            ["git", "clone", "--depth=10", repo_url, workdir],
            capture_output=True, check=True,
        )
        result = subprocess.run(
            ["git", "diff", "main", branch],
            cwd=workdir, capture_output=True, text=True,
        )
        return result.stdout[:5000]
    except Exception as e:
        logger.error(f"Could not get diff: {e}")
        return ""
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def process_task(raw: dict) -> None:
    github = GitHubClient()

    task_id = raw["id"]
    issue = raw["issue"]
    branch_name = raw["branch_name"]
    impl_result = raw.get("impl_result", {})
    repo = issue["repo"]
    issue_number = issue["number"]

    logger.info(f"Reviewing task {task_id}")
    github.post_comment(repo, issue_number, "🔍 **Revisando código…**")

    diff = get_diff(repo, branch_name)

    review = review_code(
        issue_title=issue["title"],
        issue_body=issue["body"],
        diff=diff,
        test_output=impl_result.get("test_output", ""),
        impl_summary=impl_result.get("summary", ""),
    )

    if not review.get("approved"):
        logger.warning(f"Task {task_id} blocked by review: {review.get('issues')}")
        github.post_comment(
            repo, issue_number,
            f"⚠️ **Review bloqueó el PR automático.**\n\n"
            + "\n".join(f"- {i}" for i in review.get("issues", []))
            + "\n\nRequiere revisión manual.",
        )
        github.add_label(repo, issue_number, ["factory:review-blocked"])
        return

    pr_url = create_pr(
        repo=repo,
        issue_number=issue_number,
        branch_name=branch_name,
        issue_title=issue["title"],
        impl_summary=impl_result.get("summary", ""),
        review_result=review,
        test_output=impl_result.get("test_output", ""),
    )
    logger.info(f"Task {task_id} done — {pr_url}")


def run():
    queue = QueueClient()
    logger.info("Reviewer worker started — waiting for tasks")

    while True:
        item = queue.pop(QUEUE_REVIEW, timeout=30)
        if item:
            process_task(item)


if __name__ == "__main__":
    run()
