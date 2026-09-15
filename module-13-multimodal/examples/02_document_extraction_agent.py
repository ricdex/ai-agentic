"""
Módulo 13 — Ejemplo 2: Extracción estructurada de una factura escaneada

Combina vision (Módulo 13) con el patrón de structured outputs del Módulo 7:
en vez de OCR + regex frágil, Claude lee la imagen y devuelve un JSON
validado con Pydantic directamente.

Requisitos:
    pip install anthropic pydantic

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python 02_document_extraction_agent.py path/to/invoice.jpg
"""

import base64
import mimetypes
import sys

import anthropic
from pydantic import BaseModel, ValidationError

client = anthropic.Anthropic()


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float


class Invoice(BaseModel):
    vendor_name: str
    invoice_number: str | None = None
    date: str | None = None
    line_items: list[LineItem]
    subtotal: float | None = None
    tax: float | None = None
    total: float
    currency: str = "USD"


INVOICE_TOOL = {
    "name": "extract_invoice",
    "description": "Extrae los datos estructurados de una imagen de factura o recibo",
    "input_schema": Invoice.model_json_schema(),
}


def encode_image(path: str) -> dict:
    media_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def extract_invoice(image_path: str, max_retries: int = 2) -> Invoice:
    messages = [{
        "role": "user",
        "content": [
            encode_image(image_path),
            {"type": "text", "text": "Extraé todos los datos de esta factura. Si un campo no aparece "
                                      "en la imagen, omitilo en vez de inventarlo."},
        ],
    }]

    last_error = None
    for attempt in range(max_retries + 1):
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            tools=[INVOICE_TOOL],
            tool_choice={"type": "tool", "name": "extract_invoice"},
            messages=messages,
        )
        tool_call = next(b for b in response.content if b.type == "tool_use")

        try:
            return Invoice.model_validate(tool_call.input)
        except ValidationError as e:
            last_error = e
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": f"La extracción no es válida: {e}. Corregí los campos y reintentá.",
                    "is_error": True,
                }],
            })

    raise ValueError(f"No se pudo extraer una factura válida tras {max_retries} reintentos: {last_error}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)

    invoice = extract_invoice(sys.argv[1])
    print(invoice.model_dump_json(indent=2))
