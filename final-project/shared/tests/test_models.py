from shared.models import Complexity, Issue, Task, TaskStatus, TriageResult


def test_issue_defaults_labels_to_empty_list():
    issue = Issue(number=1, title="Bug", body="...", repo="org/repo")
    assert issue.labels == []


def test_triage_result_defaults_suggested_approach_to_empty_string():
    result = TriageResult(
        automatable=True,
        complexity=Complexity.LOW,
        needs_spec=False,
        reasoning="Cambio de una línea",
    )
    assert result.suggested_approach == ""


def test_task_starts_with_zero_retries_and_a_timestamp():
    issue = Issue(number=1, title="Bug", body="...", repo="org/repo")
    triage = TriageResult(
        automatable=True, complexity=Complexity.LOW, needs_spec=False, reasoning="ok"
    )
    task = Task(id="t1", issue=issue, triage=triage, status=TaskStatus.TRIAGED)

    assert task.retries == 0
    assert task.created_at > 0
    assert task.status is TaskStatus.TRIAGED


def test_complexity_and_status_are_plain_strings_for_json_serialization():
    # QueueClient serializa el estado con json.dumps; estos enums deben
    # comportarse como str para que eso no rompa.
    assert Complexity.HIGH == "high"
    assert TaskStatus.PR_OPENED == "pr_opened"
