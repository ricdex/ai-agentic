"""
Módulo 13 — Ejemplo 3: Pipeline de audio — transcripción + agente

Claude no procesa audio nativamente (ver 13.7 del README). El patrón de
producción es transcribir localmente con faster-whisper (rápido, corre en
CPU, sin costo de API) y pasarle el texto a un agente de Claude normal.

Requisitos:
    pip install anthropic faster-whisper

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 03_audio_pipeline.py path/to/call_recording.mp3
"""

import sys

import anthropic
from faster_whisper import WhisperModel

client = anthropic.Anthropic()

TRIAGE_TOOL = {
    "name": "triage_call",
    "description": "Clasifica una llamada de soporte transcripta",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Resumen en 1-2 oraciones"},
            "customer_complaint": {"type": "string"},
            "urgency": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "requires_callback": {"type": "boolean"},
        },
        "required": ["summary", "customer_complaint", "urgency", "requires_callback"],
    },
}


def transcribe(audio_path: str) -> str:
    """Transcripción local — no llama a ninguna API externa."""
    model = WhisperModel("small", compute_type="int8")
    segments, info = model.transcribe(audio_path)
    print(f"[Transcripción: idioma detectado={info.language}, duración={info.duration:.1f}s]\n")
    return " ".join(segment.text.strip() for segment in segments)


def triage_call(transcript: str) -> dict:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # clasificación simple, no necesita el modelo más caro
        max_tokens=400,
        tools=[TRIAGE_TOOL],
        tool_choice={"type": "tool", "name": "triage_call"},
        messages=[{
            "role": "user",
            "content": f"Triage esta llamada de soporte transcripta:\n\n{transcript}",
        }],
    )
    tool_call = next(b for b in response.content if b.type == "tool_use")
    return tool_call.input


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)

    transcript = transcribe(sys.argv[1])
    print(f"Transcripción:\n{transcript}\n")

    triage = triage_call(transcript)
    print("Triage:")
    for key, value in triage.items():
        print(f"  {key}: {value}")
