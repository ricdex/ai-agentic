import os
import requests


class GitHubClient:
    def __init__(self):
        self.token = os.environ["GITHUB_TOKEN"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.base = "https://api.github.com"

    def _req(self, method: str, path: str, **kwargs) -> dict:
        resp = requests.request(
            method, f"{self.base}{path}", headers=self.headers, **kwargs
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def get_issue(self, repo: str, number: int) -> dict:
        return self._req("GET", f"/repos/{repo}/issues/{number}")

    def post_comment(self, repo: str, number: int, body: str) -> dict:
        return self._req(
            "POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body}
        )

    def add_label(self, repo: str, number: int, labels: list[str]) -> None:
        self._req(
            "POST", f"/repos/{repo}/issues/{number}/labels", json={"labels": labels}
        )

    def create_pr(
        self, repo: str, title: str, body: str, head: str, base: str = "main"
    ) -> dict:
        return self._req(
            "POST",
            f"/repos/{repo}/pulls",
            json={"title": title, "body": body, "head": head, "base": base},
        )

    def get_comments(self, repo: str, number: int) -> list[dict]:
        return self._req("GET", f"/repos/{repo}/issues/{number}/comments")

    def get_repo(self, repo: str) -> dict:
        return self._req("GET", f"/repos/{repo}")
