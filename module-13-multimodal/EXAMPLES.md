# Módulo 13 — Ejemplos con Output Esperado

---

## Ejemplo 1 — Vision básico: describir y comparar imágenes

**Archivo:** `examples/01_vision_basics.py`

Manda un screenshot local a Claude, pide una descripción, y compara dos imágenes ("antes vs después") en el mismo mensaje.

```python
def encode_image(path: str) -> dict:
    media_type = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=400,
    messages=[{
        "role": "user",
        "content": [
            encode_image("checkout_button_mobile.png"),
            {"type": "text", "text": "Describí qué se ve. Si hay un error visual, señalalo."},
        ],
    }],
)
```

**Output esperado:**

```
=== Describiendo checkout_button_mobile.png ===
La captura muestra la vista de checkout en mobile. El botón "Confirmar compra"
está parcialmente cortado en el borde derecho de la pantalla — el texto dice
"Confirmar com" y el resto queda fuera del viewport. El layout usa una grilla
de 2 columnas que no está colapsando a 1 columna en este ancho (375px), lo
que sugiere un breakpoint de CSS faltante o mal configurado.

Tokens: 1247 in / 89 out

=== Comparando before.png vs after.png ===
1. El botón "Confirmar compra" ahora es visible completo (antes cortado).
2. El layout pasó de 2 columnas a 1 columna en este ancho.
3. El color del botón cambió de azul (#2563eb) a verde (#16a34a).

Tokens: 2103 in / 47 out
```

**Qué muestra:**
- Claude no solo transcribe texto de la imagen, infiere la causa probable (breakpoint de CSS faltante) a partir de layout.
- La comparación de dos imágenes en el mismo mensaje evita mandar dos requests separados y perder el contexto de "cuál es cuál".
- El costo salta de ~1.250 a ~2.100 tokens de input al pasar de 1 a 2 imágenes — lineal con la cantidad de imágenes, no gratis.

---

## Ejemplo 2 — Extracción estructurada de una factura escaneada

**Archivo:** `examples/02_document_extraction_agent.py`

Una factura fotografiada con el celular (ligeramente rotada, con sombra) se convierte en JSON validado con Pydantic, con retry si la extracción no cumple el schema.

```python
class Invoice(BaseModel):
    vendor_name: str
    invoice_number: str | None = None
    line_items: list[LineItem]
    total: float
    currency: str = "USD"

invoice = extract_invoice("invoice_photo.jpg")
```

**Output esperado:**

```json
{
  "vendor_name": "Ferretería Industrial SRL",
  "invoice_number": "FC-A-00012845",
  "date": "2026-08-14",
  "line_items": [
    {"description": "Tornillos M6 x 40mm (caja x100)", "quantity": 3.0, "unit_price": 8500.0, "total": 25500.0},
    {"description": "Taladro percutor 750W", "quantity": 1.0, "unit_price": 145000.0, "total": 145000.0}
  ],
  "subtotal": 170500.0,
  "tax": 35805.0,
  "total": 206305.0,
  "currency": "ARS"
}
```

**Qué muestra:**
- La foto está rotada ~5° y tiene sombra de la mano sosteniendo el celular — Claude igual extrae los datos correctamente, algo que un pipeline de OCR clásico (Tesseract) suele fallar sin preprocesamiento manual.
- `currency` se infiere del contexto (formato de números, símbolo "$" ambiguo) en vez de asumir el default — Claude entiende que es ARS por el rango de montos y el layout de la factura.
- Si el modelo devuelve un `total` que no coincide matemáticamente con la suma de `line_items`, el loop de retry (igual que en Módulo 7) le devuelve el error de validación y reintenta.

---

## Ejemplo 3 — Pipeline de audio: transcripción + agente

**Archivo:** `examples/03_audio_pipeline.py`

Una grabación de una llamada de soporte se transcribe localmente con faster-whisper (sin costo de API) y el texto resultante se lo pasa a un agente de Claude para triage.

```python
def transcribe(audio_path: str) -> str:
    model = WhisperModel("small", compute_type="int8")
    segments, info = model.transcribe(audio_path)
    return " ".join(segment.text.strip() for segment in segments)
```

**Output esperado:**

```
[Transcripción: idioma detectado=es, duración=94.3s]

Transcripción:
Hola, buenas tardes, te llamo porque hice un pedido hace cinco días y todavía
no me llegó nada, el tracking dice que está en tránsito pero no se mueve
desde el martes. Ya es la tercera vez que llamo por esto y necesito una
solución porque lo necesito para un evento este fin de semana.

Triage:
  summary: Cliente reclama pedido detenido en tránsito desde hace 3 días, tercer contacto por el mismo caso.
  customer_complaint: Pedido sin movimiento en el tracking desde hace días, necesita el producto para un evento próximo.
  urgency: high
  requires_callback: True
```

**Qué muestra:**
- La transcripción corre 100% local — no hay costo de API ni el audio sale de tu infraestructura, relevante si hay datos sensibles del cliente.
- El triage usa Haiku (no Sonnet ni Opus): es clasificación simple sobre texto ya limpio, no necesita el modelo más caro — mismo criterio de selección de modelo del README principal.
- `urgency: high` no viene de una palabra clave ("urgente") sino de la combinación de señales: tercer contacto por el mismo tema + deadline concreto (el evento del fin de semana).

---

Ver el [README principal](./README.md) para los conceptos de content blocks multimodales, costos por resolución de imagen y el patrón de pipeline para audio.
