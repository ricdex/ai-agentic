import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

REVIEW_TOOLS = [{
    "name": "submit_review",
    "description": "Submit the code review result",
    "input_schema": {
        "type": "object",
        "properties": {
            "approved": {
                "type": "boolean",
                "description": "Approved to open PR?",
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Blocking issues that prevent approval",
            },
            "suggestions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Non-blocking improvement suggestions",
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence review summary",
            },
        },
        "required": ["approved", "issues", "suggestions", "summary"],
    },
}]

SYSTEM = """You are a senior engineer reviewing AI-generated code changes.

Review criteria (blocking → reject; non-blocking → suggest):
BLOCKING: doesn't solve the stated issue, tests missing for new logic, hardcoded secrets, SQL/command injection risk, silently catches all exceptions
NON-BLOCKING: style nits, minor naming, optional optimizations

Be practical. Approve if the fix is correct and safe, even if imperfect. Only reject for real problems.
Always call submit_review."""


def review_code(
    issue_title: str,
    issue_body: str,
    diff: str,
    test_output: str,
    impl_summary: str,
) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        tools=REVIEW_TOOLS,
        tool_choice={"type": "tool", "name": "submit_review"},
        messages=[{
            "role": "user",
            "content": (
                f"## Issue\n**{issue_title}**\n{issue_body}\n\n"
                f"## What was done\n{impl_summary}\n\n"
                f"## Diff\n```diff\n{diff[:4000]}\n```\n\n"
                f"## Test results\n```\n{test_output[:1000]}\n```"
            ),
        }],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_review":
            return block.input

    return {
        "approved": False,
        "issues": ["Review agent returned no output"],
        "suggestions": [],
        "summary": "Review failed",
    }
