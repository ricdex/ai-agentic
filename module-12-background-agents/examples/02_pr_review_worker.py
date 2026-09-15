import asyncio
import json
import signal
import time
from dataclasses import dataclass, field
from anthropic import Anthropic

client = Anthropic()

@dataclass
class WorkerMetrics:
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    total_cost_usd: float = 0.0
    durations: list = field(default_factory=list)

    def success_rate(self):
        total = self.processed + self.failed
        return self.processed / total if total > 0 else 1.0

    def avg_cost(self):
        return self.total_cost_usd / self.processed if self.processed else 0

    def p95_duration(self):
        if not self.durations:
            return 0
        s = sorted(self.durations)
        return s[int(len(s) * 0.95)]

    def print_report(self):
        print("\n=== Reporte del worker ===")
        print(f"  Procesados:     {self.processed}")
        print(f"  Fallidos:       {self.failed}")
        print(f"  Salteados:      {self.skipped}")
        print(f"  Success rate:   {self.success_rate():.1%}")
        print(f"  Costo total:    ${self.total_cost_usd:.4f}")
        print(f"  Costo/evento:   ${self.avg_cost():.4f}")
        print(f"  p95 duración:   {self.p95_duration():.2f}s")

# Modelos según complejidad estimada del diff
def choose_model(diff: str) -> str:
    lines_changed = diff.count('\n')
    if lines_changed > 100:
        return "claude-sonnet-5"   # diffs grandes requieren más razonamiento
    return "claude-haiku-4-5-20251001"      # diffs pequeños, más rápido y barato

# Simular cola con eventos de distinta complejidad
QUEUE = [
    {"id": "pr-101", "pr_number": 101, "title": "Fix typo in README", "diff": "- Wellcome\n+ Welcome", "complexity": "trivial"},
    {"id": "pr-102", "pr_number": 102, "title": "Refactor payment processor", "diff": "\n".join([f"  line {i}" for i in range(120)]), "complexity": "alta"},
    {"id": "pr-103", "pr_number": 103, "title": "Add input validation", "diff": "+ if not user_input:\n+     raise ValueError('required')", "complexity": "media"},
    {"id": "pr-104", "pr_number": 103, "title": "Add input validation", "diff": "+ if not user_input:\n+     raise ValueError('required')", "complexity": "media"},  # duplicado intencional
]

PROCESSED = set()
metrics = WorkerMetrics()
running = True

def handle_shutdown(sig, frame):
    global running
    print("\n⚠ Shutdown signal recibido. Terminando ejecución actual...")
    running = False

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

REVIEW_PROMPT = """Revisá este PR. Sé específico y conciso. Solo problemas reales.
Formato: bullets. Si no hay problemas, decí "Sin observaciones críticas." """

def process_pr(event: dict) -> dict:
    if event["id"] in PROCESSED:
        return {"status": "skipped"}

    model = choose_model(event["diff"])
    start = time.time()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=400,
            system=[{"type": "text", "text": REVIEW_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"PR #{event['pr_number']}: {event['title']}\n\n{event['diff']}"}]
        )

        # Calcular costo aproximado (precios Haiku/Sonnet)
        input_t = response.usage.input_tokens
        output_t = response.usage.output_tokens
        cached_t = response.usage.cache_read_input_tokens
        if "haiku" in model:
            cost = (input_t * 0.8 + output_t * 4.0 + cached_t * 0.08) / 1_000_000
        else:
            cost = (input_t * 3.0 + output_t * 15.0 + cached_t * 0.30) / 1_000_000

        PROCESSED.add(event["id"])
        duration = time.time() - start

        return {
            "status": "ok",
            "model": model.split("-")[1],  # "haiku" o "sonnet"
            "review": response.content[0].text,
            "cost_usd": cost,
            "duration_s": duration,
            "cache_pct": int(cached_t / input_t * 100) if input_t else 0
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

def run_worker():
    print("PR Review Worker v1.0")
    print("=" * 40)

    for event in QUEUE:
        if not running:
            print("Worker detenido por shutdown signal.")
            break

        print(f"\n→ [{event['id']}] PR #{event['pr_number']} ({event['complexity']})")
        result = process_pr(event)

        if result["status"] == "skipped":
            metrics.skipped += 1
            print(f"  ↷ Saltado (ya procesado)")

        elif result["status"] == "error":
            metrics.failed += 1
            print(f"  ✗ Error: {result['error']}")

        else:
            metrics.processed += 1
            metrics.total_cost_usd += result["cost_usd"]
            metrics.durations.append(result["duration_s"])

            print(f"  ✓ Modelo: {result['model']} | {result['duration_s']:.2f}s | ${result['cost_usd']:.5f} | caché: {result['cache_pct']}%")
            print(f"  Review: {result['review'][:200]}{'...' if len(result['review']) > 200 else ''}")

    metrics.print_report()

run_worker()
