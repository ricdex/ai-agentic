"""
Módulo 13 — Ejemplo 1: Vision básico — describir y comparar imágenes

Demuestra:
- Cómo mandar una imagen local a Claude (base64)
- Describir un screenshot con un error de UI
- Comparar dos imágenes en el mismo mensaje ("antes vs después")
- Medir el costo real en tokens de una llamada con imagen

Requisitos:
    pip install anthropic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 01_vision_basics.py path/to/before.png path/to/after.png
"""

import base64
import mimetypes
import sys

import anthropic

client = anthropic.Anthropic()


def encode_image(path: str) -> dict:
    media_type = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def describe_image(path: str) -> None:
    print(f"=== Describiendo {path} ===")
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": [
                encode_image(path),
                {"type": "text", "text": "Describí qué se ve en esta captura de pantalla. "
                                          "Si hay un error o algo visualmente roto, señalalo específicamente."},
            ],
        }],
    )
    print(response.content[0].text)
    print(f"\nTokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out\n")


def compare_images(before_path: str, after_path: str) -> None:
    print(f"=== Comparando {before_path} vs {after_path} ===")
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Imagen ANTES:"},
                encode_image(before_path),
                {"type": "text", "text": "Imagen DESPUÉS:"},
                encode_image(after_path),
                {"type": "text", "text": "¿Qué cambió entre las dos capturas? Listá solo diferencias "
                                          "visuales concretas (layout, texto, colores), no especules sobre causas."},
            ],
        }],
    )
    print(response.content[0].text)
    print(f"\nTokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    describe_image(sys.argv[1])

    if len(sys.argv) >= 3:
        compare_images(sys.argv[1], sys.argv[2])
