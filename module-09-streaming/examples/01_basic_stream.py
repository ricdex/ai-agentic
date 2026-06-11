"""
Módulo 9 — Ejemplo 1: Streaming básico con métricas

Demuestra:
- Cómo usar client.messages.stream()
- Métricas de TTFT (Time to First Token) y latencia total
- Comparación con llamada sin streaming para notar la diferencia de UX

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 01_basic_stream.py
"""

import time
import anthropic

client = anthropic.Anthropic()

PROMPT = """Analizá el siguiente código Python y describí:
1. Qué hace
2. Potenciales problemas
3. Cómo mejorarías la gestión de errores

```python
def process_payment(user_id, amount, card_token):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    if user:
        result = stripe.charge(card_token, amount)
        db.execute(f"UPDATE users SET balance = balance - {amount} WHERE id = {user_id}")
        return result
    return None
```
"""


def demo_without_streaming():
    """La UX sin streaming: silencio total hasta tener la respuesta completa."""
    print("=== SIN streaming ===")
    print("Enviando request... (el usuario espera en silencio)")
    start = time.time()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": PROMPT}]
    )

    elapsed = time.time() - start
    text = response.content[0].text
    print(f"[Respuesta completa apareció después de {elapsed:.2f}s]")
    print(text[:200] + "...")
    print(f"\nTokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
    print()


def demo_with_streaming():
    """La UX con streaming: el usuario ve el output a medida que se genera."""
    print("=== CON streaming ===")
    print("Enviando request...")

    start = time.time()
    first_token_time = None
    token_count = 0

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": PROMPT}]
    ) as stream:
        for text in stream.text_stream:
            if first_token_time is None:
                first_token_time = time.time()
                ttft = first_token_time - start
                print(f"[Primer token en {ttft:.2f}s]\n")

            print(text, end="", flush=True)
            token_count += 1

        final = stream.get_final_message()

    total = time.time() - start
    ttft = (first_token_time - start) if first_token_time else total

    print(f"\n\n--- Métricas ---")
    print(f"  TTFT:           {ttft:.2f}s  (Time to First Token)")
    print(f"  Latencia total: {total:.2f}s")
    print(f"  Tokens:         {final.usage.input_tokens} in / {final.usage.output_tokens} out")
    print(f"  Throughput:     {final.usage.output_tokens / total:.0f} tokens/s")


if __name__ == "__main__":
    demo_without_streaming()
    print("-" * 60)
    print()
    demo_with_streaming()
