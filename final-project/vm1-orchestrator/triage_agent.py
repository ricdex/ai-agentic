import os
import anthropic
from shared.models import TriageResult, Complexity

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TRIAGE_TOOLS = [{
    "name": "submit_triage",
    "description": "Submit the triage decision for this issue",
    "input_schema": {
        "type": "object",
        "properties": {
            "automatable": {
                "type": "boolean",
                "description": "Can this be fully automated end-to-end?",
            },
            "complexity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "low = <1h, medium = 1-4h, high = >4h",
            },
            "needs_spec": {
                "type": "boolean",
                "description": "Is the requirement ambiguous enough to need a spec before coding?",
            },
            "reasoning": {"type": "string"},
            "suggested_approach": {
                "type": "string",
                "description": "Brief technical approach (1-2 sentences)",
            },
        },
        "required": ["automatable", "complexity", "needs_spec", "reasoning"],
    },
}]

SYSTEM = """You are a triage agent in a software factory. Analyze GitHub issues and decide:
1. automatable: true only for clear bug fixes, small features with clear acceptance criteria, test additions, or focused refactors
2. complexity: low (<1h), medium (1-4h), high (>4h)
3. needs_spec: true only for high complexity or genuinely ambiguous requirements

NOT automatable: architecture decisions, security changes without clear spec, major refactors, issues needing external input.

Always call submit_triage."""


def triage_issue(title: str, body: str, repo: str) -> TriageResult:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        tools=TRIAGE_TOOLS,
        tool_choice={"type": "tool", "name": "submit_triage"},
        messages=[{
            "role": "user",
            "content": f"Repo: {repo}\n\nTitle: {title}\n\nBody:\n{body or '(no description)'}",
        }],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_triage":
            d = block.input
            return TriageResult(
                automatable=d["automatable"],
                complexity=Complexity(d["complexity"]),
                needs_spec=d.get("needs_spec", False),
                reasoning=d["reasoning"],
                suggested_approach=d.get("suggested_approach", ""),
            )

    return TriageResult(
        automatable=False,
        complexity=Complexity.HIGH,
        needs_spec=True,
        reasoning="Triage returned no result — defaulting to manual",
    )


def generate_spec(title: str, body: str, approach: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=[{
            "type": "text",
            "text": (
                "Generate a concise technical spec. Include: "
                "**Problem**, **Proposed solution**, **Acceptance criteria** (checkboxes), **Out of scope**. "
                "Keep under 350 words."
            ),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": f"Issue: {title}\n\nDetails:\n{body}\n\nSuggested approach: {approach}",
        }],
    )
    return response.content[0].text
