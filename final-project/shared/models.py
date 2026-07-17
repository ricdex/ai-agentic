from dataclasses import dataclass, field
from enum import Enum
import time


class Complexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(str, Enum):
    TRIAGED = "triaged"
    SPEC_PENDING = "spec_pending"
    IMPLEMENTING = "implementing"
    REVIEWING = "reviewing"
    PR_OPENED = "pr_opened"
    FAILED = "failed"


@dataclass
class Issue:
    number: int
    title: str
    body: str
    repo: str
    labels: list[str] = field(default_factory=list)


@dataclass
class TriageResult:
    automatable: bool
    complexity: Complexity
    needs_spec: bool
    reasoning: str
    suggested_approach: str = ""


@dataclass
class Task:
    id: str
    issue: Issue
    triage: TriageResult
    status: TaskStatus
    branch_name: str = ""
    spec: str = ""
    retries: int = 0
    created_at: float = field(default_factory=time.time)
