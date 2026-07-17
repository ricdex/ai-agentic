import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class Sandbox:
    """Isolated git workspace for a single implementation task."""

    def __init__(self, repo: str, branch_name: str):
        self.repo = repo
        self.branch_name = branch_name
        self.workdir: str | None = None
        self._repo_url = (
            f"https://x-access-token:{os.environ['GITHUB_TOKEN']}"
            f"@github.com/{repo}.git"
        )

    def __enter__(self):
        self.workdir = tempfile.mkdtemp(prefix="factory_impl_")
        logger.info(f"Sandbox: {self.workdir}")

        self._git(["clone", "--depth=1", self._repo_url, self.workdir])
        self._git(["config", "user.email", "factory@automated.dev"])
        self._git(["config", "user.name", "Software Factory"])
        self._git(["checkout", "-b", self.branch_name])
        return self

    def __exit__(self, *_):
        if self.workdir and os.path.exists(self.workdir):
            shutil.rmtree(self.workdir)
            logger.info(f"Sandbox cleaned: {self.workdir}")

    def _git(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=self.workdir,
            capture_output=True,
            text=True,
            check=True,
        )

    def _run(self, cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, cwd=self.workdir, capture_output=True, text=True, timeout=timeout
        )

    def _safe_path(self, path: str) -> str | None:
        full = os.path.realpath(os.path.join(self.workdir, path))
        if not full.startswith(os.path.realpath(self.workdir)):
            return None
        return full

    # ── Tools exposed to the agent ──────────────────────────────────────────

    def read_file(self, path: str) -> str:
        full = self._safe_path(path)
        if not full:
            return "ERROR: path traversal denied"
        if not os.path.exists(full):
            return f"ERROR: file not found: {path}"
        try:
            with open(full) as f:
                return f.read()
        except Exception as e:
            return f"ERROR: {e}"

    def write_file(self, path: str, content: str) -> str:
        full = self._safe_path(path)
        if not full:
            return "ERROR: path traversal denied"
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        return f"Written: {path} ({len(content)} chars)"

    def search_code(self, pattern: str, file_pattern: str = "*.py") -> str:
        result = self._run(
            ["grep", "-r", "-n", "--include", file_pattern, pattern, "."]
        )
        output = result.stdout.strip()
        return output[:3000] if output else "No matches found"

    def list_files(self, directory: str = ".") -> str:
        result = self._run([
            "find", directory, "-type", "f",
            "-not", "-path", "*/.git/*",
            "-not", "-path", "*/__pycache__/*",
            "-not", "-path", "*/node_modules/*",
        ])
        return result.stdout[:2000] or "(empty)"

    def run_tests(self, test_path: str = "") -> tuple[bool, str]:
        result = self._run(
            ["python", "-m", "pytest", test_path or ".", "-v", "--tb=short"],
            timeout=120,
        )
        passed = result.returncode == 0
        output = (result.stdout + result.stderr)[:3000]
        return passed, output

    def commit_and_push(self, message: str) -> bool:
        try:
            self._git(["add", "-A"])
            self._git(["commit", "-m", message])
            self._git(["push", "-u", "origin", self.branch_name])
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git push failed: {e.stderr}")
            return False

    def get_diff(self) -> str:
        try:
            result = self._git(["diff", "HEAD~1", "HEAD", "--stat"])
            return result.stdout
        except Exception:
            return ""
