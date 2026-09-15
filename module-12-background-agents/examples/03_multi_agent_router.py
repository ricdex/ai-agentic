import json
from anthropic import Anthropic

client = Anthropic()

# ── Agentes especializados ──────────────────────────────────────

def agent_pr_review(event: dict) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system="Sos un code reviewer. Revisá el diff. Máximo 3 bullets.",
        messages=[{"role": "user", "content": f"PR: {event['title']}\nDiff: {event.get('diff', 'N/A')}"}]
    )
    return response.content[0].text

def agent_issue_triage(event: dict) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system="""Triageá este issue. Respondé en JSON con exactamente estos campos:
{"severity": "low|medium|high|critical", "category": "bug|feature|question|docs", "needs_clarification": true|false}""",
        messages=[{"role": "user", "content": f"Issue: {event['title']}\n{event.get('body', '')}"}]
    )
    return response.content[0].text

def agent_ci_fix(event: dict) -> str:
    response = client.messages.create(
        model="claude-sonnet-5",  # CI failures requieren más razonamiento
        max_tokens=500,
        system="Analizá el log de CI y explicá la causa raíz y el fix más probable. Sé específico.",
        messages=[{"role": "user", "content": f"CI failure en {event['workflow']}:\n{event.get('log', 'N/A')}"}]
    )
    return response.content[0].text

# ── Router ──────────────────────────────────────────────────────

ROUTES = {
    "pr_opened":        ("PR Review Agent",   agent_pr_review),
    "pr_synchronize":   ("PR Review Agent",   agent_pr_review),
    "issues_opened":    ("Issue Triage Agent", agent_issue_triage),
    "workflow_failure": ("CI Fix Agent",       agent_ci_fix),
}

def route_and_process(event: dict) -> dict:
    event_type = event["type"]

    if event_type not in ROUTES:
        return {"status": "ignored", "type": event_type}

    agent_name, agent_fn = ROUTES[event_type]
    print(f"  → Despachando a: {agent_name}")

    result = agent_fn(event)
    return {"status": "processed", "agent": agent_name, "output": result}

# ── Simulación de eventos mezclados ─────────────────────────────

EVENTS = [
    {
        "id": "e1", "type": "pr_opened",
        "title": "Add rate limiting to login endpoint",
        "diff": "+ @rate_limit(max_calls=5, period=60)\n  def login(request):\n      ..."
    },
    {
        "id": "e2", "type": "issues_opened",
        "title": "App crashes on logout when session is expired",
        "body": "Steps to reproduce: 1) Login 2) Wait 2 hours 3) Click logout → 500 error"
    },
    {
        "id": "e3", "type": "workflow_failure",
        "workflow": "CI / test (python 3.11)",
        "log": "FAILED tests/test_auth.py::test_login_rate_limit - AttributeError: 'NoneType' object has no attribute 'remaining_calls'\n  File 'src/middleware.py', line 42, in check_rate_limit"
    },
    {
        "id": "e4", "type": "pr_review_requested",  # tipo no registrado
        "title": "..."
    },
]

print("Multi-Agent Router")
print("=" * 40)

for event in EVENTS:
    print(f"\n[{event['id']}] Tipo: {event['type']}")
    result = route_and_process(event)

    if result["status"] == "ignored":
        print(f"  ↷ Ignorado (sin agente para este tipo)")
    else:
        print(f"  ✓ {result['agent']} respondió:")
        print(f"  {result['output']}")
