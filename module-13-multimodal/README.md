# Módulo 13 — Agentes Multimodales

> "Un agente que solo lee texto no puede revisar un screenshot roto, leer una factura escaneada ni ver el gráfico de errores que vos ves. Vision no es un extra — es otro sentido."

---

## Paso a paso

1. Ejecutá `examples/01_vision_basics.py` y comparás cómo Claude describe e interpreta una imagen (screenshot, gráfico, diagrama).
2. Ejecutá `02_document_extraction_agent.py`: extraé datos estructurados de un documento escaneado (factura, recibo) combinando vision con el patrón de structured outputs del [Módulo 7](../module-07-structured-outputs/README.md).
3. Medí el costo real en tokens de mandar imágenes antes de meter vision en un loop agéntico (13.6).
4. Solo si el caso lo requiere, agregá `03_audio_pipeline.py` — audio necesita un paso de transcripción antes de Claude, no es nativo.

**Complejidad a evitar:** mandar imágenes de alta resolución sin resize cuando el detalle no lo justifica — es la forma más común de inflar costos en agentes multimodales.

---

## 13.1 Qué es "multimodal" para un agente, en la práctica

Claude procesa **texto e imágenes** en el mismo mensaje — no hay una API separada de "vision", es el mismo `messages.create()` con un content block distinto:

```python
{
    "role": "user",
    "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
        {"type": "text", "text": "¿Qué error se ve en este screenshot?"}
    ]
}
```

**Lo que Claude SÍ procesa nativamente:** imágenes (JPEG, PNG, GIF, WebP) y PDFs (como `document`, combinando texto extraído + render de cada página — útil para PDFs escaneados donde no hay texto seleccionable).

**Lo que Claude NO procesa nativamente:** audio y video. Para esos casos el patrón es un pipeline: transcripción/extracción de frames por fuera, y el resultado (texto) se lo pasás a Claude. Ver 13.7.

---

## 13.2 Casos de uso reales para un AI Engineer

| Caso | Por qué vision, no OCR clásico | Módulo relacionado |
|---|---|---|
| QA visual: comparar un screenshot contra el diseño esperado | Entiende layout y semántica, no solo pixeles | [Módulo 3](../module-03-dev-workflows/README.md) |
| Extracción de facturas/recibos escaneados | Entiende contexto y estructura aunque el escaneo esté rotado o borroso | [Módulo 7](../module-07-structured-outputs/README.md) |
| Leer un gráfico de error rate o un dashboard y explicar qué pasó | Interpreta tendencias visuales, no solo texto de ejes | [Módulo 5](../module-05-production/README.md) |
| Revisar un diagrama de arquitectura y detectar inconsistencias con el código | Combina comprensión visual con razonamiento sobre texto | [Módulo 0](../module-00-developer-workflow/README.md) |

**Regla:** si el dato ya existe como texto (logs, JSON, HTML), no lo conviertas a imagen para mandárselo a Claude — vision cuesta más tokens que texto y es más lenta. Usalo cuando el layout/lo visual **es** la información.

---

## 13.3 Vision básico

```python
import base64
import anthropic

client = anthropic.Anthropic()

with open("screenshot.png", "rb") as f:
    image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=500,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
            },
            {"type": "text", "text": "Describí qué error de UI se ve, si hay alguno."},
        ],
    }],
)
print(response.content[0].text)
```

Varias imágenes en el mismo mensaje funcionan igual — útil para "antes vs después" o comparar múltiples screenshots de un mismo flujo.

---

## 13.4 Extracción estructurada desde imágenes

El patrón de structured outputs del Módulo 7 (Pydantic + tool schema) funciona igual con imágenes — el content block cambia, el resto del pipeline no:

```python
response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    tools=[invoice_tool_schema],   # generado desde un modelo Pydantic, como en 7.2
    tool_choice={"type": "tool", "name": "extract_invoice"},
    messages=[{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
            {"type": "text", "text": "Extraé los datos de esta factura."},
        ],
    }],
)
invoice = Invoice.model_validate(response.content[0].input)
```

Esto es lo que reemplaza un pipeline clásico de OCR + regex + reglas de negocio frágiles: Claude entiende el layout de la factura (aunque el formato varíe entre proveedores) y devuelve el JSON ya validado.

---

## 13.5 Vision + tool use: un agente que "ve" antes de actuar

El patrón más potente: el agente toma una acción (ej. `take_screenshot`), analiza el resultado visual, y decide el siguiente paso — como un QA humano.

```
Iteración 1: agente llama take_screenshot() → recibe imagen
Iteración 2: agente analiza la imagen → "el botón de checkout está fuera de la pantalla en mobile"
Iteración 3: agente llama report_bug(description=..., screenshot=...) o propone el fix
```

El resultado de un tool call puede ser un content block de imagen, igual que el de texto:

```python
tool_results.append({
    "type": "tool_result",
    "tool_use_id": block.id,
    "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}}
    ],
})
```

---

## 13.6 Costos y límites — la parte que se olvida

Una imagen consume tokens según su resolución, no es gratis:

```
tokens ≈ (ancho_px × alto_px) / 750
```

Una captura de pantalla típica de 1920×1080 sin resize son ~2.765 tokens — más que un párrafo largo de texto. En un loop agéntico que manda screenshots en cada iteración, esto se acumula rápido.

**Checklist antes de meter vision en un loop:**
- [ ] Redimensioná la imagen al mínimo necesario para el detalle que necesitás (max ~1568px de lado suele alcanzar)
- [ ] No mandes la misma imagen sin cambios en iteraciones sucesivas — cacheala o referenciala por id
- [ ] Si el agente solo necesita saber "¿hubo un cambio?", considerá un diff perceptual (fuera de Claude) antes de gastar tokens en describir la imagen entera
- [ ] Medí el costo real con `response.usage`, igual que en el [Módulo 5](../module-05-production/README.md#54-costos-cómo-no-arruinarte)

---

## 13.7 Audio: Claude no lo procesa nativamente

A diferencia de imágenes, Claude no acepta audio como content block. El patrón de producción es un pipeline de dos etapas:

```
Audio → transcripción local (Whisper/faster-whisper) → texto → Claude (agente normal)
```

```python
from faster_whisper import WhisperModel

model = WhisperModel("small")  # corre local, sin costo de API
segments, _ = model.transcribe("call_recording.mp3")
transcript = " ".join(s.text for s in segments)

# A partir de acá es un agente de texto normal — todo lo del Módulo 1 aplica
response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=500,
    messages=[{"role": "user", "content": f"Resumí esta llamada de soporte:\n\n{transcript}"}],
)
```

**Por qué esto importa para un AI Engineer:** "agente multimodal" no significa que un solo modelo hace todo — significa orquestar el modelo correcto para cada modalidad (transcripción local barata, razonamiento con Claude) y unirlos en un pipeline, el mismo principio de composición del [Módulo 2](../module-02-workflow-design/README.md).

---

## Ejemplos con output

El código completo y el output esperado de cada ejemplo están en [EXAMPLES.md](./EXAMPLES.md):

| Ejemplo | Qué demuestra |
|---|---|
| [01 — Vision básico](./EXAMPLES.md#ejemplo-1--vision-básico-describir-y-comparar-imágenes) | Claude describe un error de UI en un screenshot y detecta la diferencia entre dos versiones |
| [02 — Extracción de documentos](./EXAMPLES.md#ejemplo-2--extracción-estructurada-de-una-factura-escaneada) | Una factura escaneada (rotada, con ruido) se convierte en JSON validado con Pydantic |
| [03 — Pipeline de audio](./EXAMPLES.md#ejemplo-3--pipeline-de-audio-transcripción--agente) | Una grabación de soporte se transcribe local y el agente extrae la queja y la urgencia |

---

## Ejercicio

Extendé el `issue_solver.py` del [Módulo 3](../module-03-dev-workflows/README.md) para que acepte issues con screenshots adjuntos:

1. Si el issue tiene una imagen adjunta (bug visual), el agente debe describir qué ve antes de tocar código
2. Compará esa descripción contra el comportamiento esperado que describe el título del issue
3. Solo si hay una discrepancia clara, el agente procede a buscar la causa en el código
4. Registrá el costo en tokens de la llamada con imagen vs una llamada de solo texto — cuantificá la diferencia

Esto es el patrón real detrás de agentes de QA visual: no reemplazan el razonamiento sobre código, lo complementan con lo que el código no puede decirte por sí solo.

---

Anterior: [Módulo 12 → Background Agents](../module-12-background-agents/README.md) · Siguiente: [Módulo 14 → Fine-tuning](../module-14-fine-tuning/README.md)
