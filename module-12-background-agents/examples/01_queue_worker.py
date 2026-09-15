import asyncio
import json
import time
from anthropic import Anthropic

client = Anthropic()

# Simular cola con una lista en memoria (en prod: Redis o SQS)
QUEUE = [
    {"id": "evt-001", "type": "pr_opened", "pr_number": 42, "title": "Fix auth token expiry", "diff": "- expires = 3600\n+ expires = 86400"},
    {"id": "evt-002", "type": "pr_opened", "pr_number": 43, "title": "Add user avatar", "diff": "+ avatar_url = models.URLField(null=True)"},
    {"id": "evt-003", "type": "pr_opened", "pr_number": 44, "title": "Remove unused imports", "diff": "- import os\n- import sys\n  import json"},
]

PROCESSED = set()  # idempotencia en memoria (en prod: Redis SET o tabla DB)

SYSTEM_PROMPT = """Sos un code reviewer. Revisá el diff y dá máximo 3 puntos concisos.
Formato: bullet points, sin intro. Solo problemas reales, no opiniones de estilo."""

def process_event(event: dict) -> dict:
    if event["id"] in PROCESSED:
        return {"skipped": True, "reason": "ya procesado"}

    start = time.time()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Haiku para reviews simples
        max_tokens=300,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{
            "role": "user",
            "content": f"PR #{event['pr_number']}: {event['title']}\n\nDiff:\n{event['diff']}"
        }]
    )

    PROCESSED.add(event["id"])
    return {
        "pr_number": event["pr_number"],
        "review": response.content[0].text,
        "tokens": response.usage.input_tokens + response.usage.output_tokens,
        "cached_tokens": response.usage.cache_read_input_tokens,
        "duration_s": round(time.time() - start, 2)
    }

def worker_loop():
    print("Worker iniciado. Procesando cola...\n")
    for message in QUEUE:
        print(f"→ Procesando evento {message['id']}...")
        result = process_event(message)
        if result.get("skipped"):
            print(f"  ↷ Saltado: {result['reason']}\n")
        else:
            print(f"  PR #{result['pr_number']} revisado en {result['duration_s']}s")
            print(f"  Tokens: {result['tokens']} ({result['cached_tokens']} en caché)")
            print(f"  Review:\n{result['review']}\n")

    # Simular segundo paso (idempotencia)
    print("--- Segundo ciclo (mismo queue, debe saltear todo) ---\n")
    for message in QUEUE:
        result = process_event(message)
        print(f"  {message['id']}: {'saltado ✓' if result.get('skipped') else 'procesado'}")

worker_loop()
