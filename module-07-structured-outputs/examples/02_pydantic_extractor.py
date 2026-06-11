"""
Módulo 7 — Ejemplo 2: Extractor con Pydantic + retry

Pipeline completo de extracción de información estructurada:
- Definición de schema con Pydantic (con validaciones)
- Generación automática del tool schema desde el modelo Pydantic
- Retry con feedback cuando la validación falla
- Ejemplo de uso: extraer incidentes de logs/reportes de texto libre

Requisitos:
    pip install anthropic pydantic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 02_pydantic_extractor.py
"""

import json
from typing import Literal
from pydantic import BaseModel, field_validator, model_validator
import anthropic

client = anthropic.Anthropic()


# --- Schema del dominio ---

class AffectedService(BaseModel):
    name: str
    error_rate_percent: float | None = None
    is_completely_down: bool = False


class Incident(BaseModel):
    title: str
    severity: Literal["P1", "P2", "P3", "P4"]
    affected_services: list[AffectedService]
    start_time_utc: str | None = None
    user_impact_percent: float | None = None
    root_cause_hypothesis: str | None = None
    immediate_actions_taken: list[str] = []
    requires_postmortem: bool

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title no puede estar vacío")
        return v.strip()

    @model_validator(mode="after")
    def p1_requires_postmortem(self) -> "Incident":
        if self.severity == "P1" and not self.requires_postmortem:
            raise ValueError("Incidentes P1 siempre requieren postmortem")
        return self


def pydantic_to_tool_schema(model: type[BaseModel], tool_name: str, description: str) -> dict:
    """Convierte un modelo Pydantic en un tool schema para Claude."""
    schema = model.model_json_schema()
    return {
        "name": tool_name,
        "description": description,
        "input_schema": schema
    }


# --- Extractor con retry ---

def extract_incident(report_text: str, max_retries: int = 2) -> Incident:
    tool = pydantic_to_tool_schema(
        Incident,
        "submit_incident",
        "Enviá los datos estructurados del incidente extraídos del reporte"
    )

    messages = [{
        "role": "user",
        "content": f"Extraé la información del siguiente reporte de incidente:\n\n{report_text}"
    }]

    last_error = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            messages.append({
                "role": "user",
                "content": (
                    f"Tu respuesta anterior falló validación con el error: {last_error}. "
                    "Corregí el campo con problema y reenviá."
                )
            })

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=[tool],
            tool_choice={"type": "tool", "name": "submit_incident"},
            messages=messages
        )

        raw = next(b for b in response.content if b.type == "tool_use").input

        try:
            return Incident(**raw)
        except Exception as e:
            last_error = str(e)
            messages.append({"role": "assistant", "content": response.content})
            if attempt == max_retries:
                raise ValueError(f"No se pudo parsear el incidente después de {max_retries + 1} intentos: {e}")

    raise RuntimeError("unreachable")


# --- Demo ---

SAMPLE_REPORTS = [
    """
    INCIDENT REPORT - 2024-01-15

    Started noticing errors around 14:30 UTC. The payment service is returning 503s
    on approximately 45% of requests. The checkout flow is broken for roughly a third
    of our users. Auth service seems fine.

    We've already rolled back the deploy from 13:45 UTC — that seems to have been the trigger.
    The on-call engineer is investigating database connection pool exhaustion.

    This is bad — we're losing ~$20k/minute in GMV.
    """,

    """
    Hey team, the dashboard is loading slowly again. Maybe 8-10 seconds for some users.
    Started this morning, not sure exactly when. Seems to affect the analytics section mostly.
    The API itself is fine, just the frontend rendering.
    """,

    """
    CRITICAL OUTAGE: Auth service completely down since 09:15 UTC.
    100% of login attempts failing. ALL services affected since nothing can authenticate.
    Team is working on it. Database disk full — clearing old logs now.
    ETA to restore: 20 minutes.
    """
]


if __name__ == "__main__":
    for i, report in enumerate(SAMPLE_REPORTS, 1):
        print(f"\n--- Reporte {i} ---")
        print(report.strip()[:100] + "...")
        print()

        try:
            incident = extract_incident(report)

            print(f"  Título:        {incident.title}")
            print(f"  Severidad:     {incident.severity}")
            print(f"  Servicios:     {[s.name for s in incident.affected_services]}")
            if incident.user_impact_percent:
                print(f"  Impacto:       {incident.user_impact_percent}% de usuarios")
            if incident.root_cause_hypothesis:
                print(f"  Hipótesis:     {incident.root_cause_hypothesis}")
            if incident.immediate_actions_taken:
                print(f"  Acciones:      {incident.immediate_actions_taken}")
            print(f"  Postmortem:    {'Sí' if incident.requires_postmortem else 'No'}")

        except ValueError as e:
            print(f"  ERROR: {e}")
