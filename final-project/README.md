# Proyecto Final — Software Factory

> "El objetivo no es que el agente reemplace al desarrollador. Es que un solo desarrollador opere con la productividad de diez."
> — Zach Lloyd, Warp

Este proyecto implementa una **software factory** funcional: un sistema que automatiza el ciclo de desarrollo completo desde que se abre un issue hasta que el PR está listo para merge.

---

## Qué hace

```
GitHub Issue abierto
        │
        ▼
┌──────────────────┐
│  VM1: Orchestrator│  Recibe el webhook · Triage · Spec (si aplica)
│  + Spec Watcher  │
└────────┬─────────┘
         │ Redis queue
         ▼
┌──────────────────┐
│  VM2: Implementor │  Clona repo · Escribe código · Corre tests · Retry
└────────┬─────────┘
         │ Redis queue
         ▼
┌──────────────────┐
│  VM3: Reviewer   │  Code review · Verifica tests · Abre PR · Notifica
└──────────────────┘
         │
         ▼
  Human review  ←  único gate humano
  + merge PR
```

**Lo que hace el humano:** abrir el issue + revisar y mergear el PR. Nada más.

---

## Qué cubre del SDLC

| Stage | Quién | Notas |
|---|---|---|
| Triage | Agente (Haiku) | Decide si es automatable y la complejidad |
| Spec | Agente (Sonnet) | Solo para issues complejos/ambiguos |
| Implement | Agente (Sonnet/Opus) | ReAct loop con tools, retry automático |
| Code review | Agente (Sonnet) | Structured output, bloquea si hay issues reales |
| Verify | Tests reales | Corre pytest en entorno limpio |
| PR | Automatico | Summary completo del proceso |
| Monitor | (extensión futura) | Ver módulo 12 |

---

## Qué módulos del curso aplica

| Módulo | Concepto | Dónde |
|---|---|---|
| 01 | ReAct loop + tool use | `implementation_agent.py` |
| 02 | Feedback loop / retry | `vm2-implementor/main.py` MAX_RETRIES |
| 03 | Prompt caching | `cache_control: ephemeral` en todos los system prompts |
| 04 | Model routing por complejidad | Haiku→Sonnet→Opus según retry y complejidad |
| 05 | Observabilidad | Logs estructurados en cada VM |
| 07 | Structured outputs | `tool_choice: {type: tool}` en triage y review |
| 09 | Background workers | Queue workers en VM2 y VM3 |
| 11 | Deployment | Dockerfile + Terraform |
| 12 | Agentes persistentes | Workers corriendo 24/7 en VMs |

---

## Prerrequisitos

- Docker + Docker Compose (para correr local)
- Python 3.11+ (para el script de simulación)
- Cuenta Anthropic con acceso a Claude Sonnet y Haiku
- GitHub token con scopes: `repo`, `issues`, `pull_requests`
- (Para cloud) AWS CLI + Terraform >= 1.5

---

## Setup local (con docker-compose)

### 1. Copiar configuración

```bash
cp .env.example .env
# Editar .env con tus keys reales
```

### 2. Crear el demo repo en GitHub

```bash
# Crear repo en tu cuenta GitHub (público o privado)
# Subir el contenido de demo-repo/ como la base del repo
cd demo-repo
git init && git add -A
git commit -m "initial: calculator with bugs"
git remote add origin https://github.com/TU_USER/factory-demo
git push -u origin main
```

### 3. Configurar el webhook

En GitHub → `factory-demo` → Settings → Webhooks → Add webhook:
- Payload URL: `http://localhost:8000/webhook` (o tu URL de ngrok)
- Content type: `application/json`
- Secret: el mismo valor de `GITHUB_WEBHOOK_SECRET` en tu `.env`
- Events: **Issues** (solo Issues)

Para exponer local con ngrok:
```bash
ngrok http 8000
# Copiar la URL https://xxx.ngrok.io/webhook al webhook
```

### 4. Levantar el factory

```bash
make up
# O directamente:
docker compose up --build -d
```

### 5. Verificar que todo corre

```bash
docker compose logs -f
# Deberías ver:
# [orchestrator] Uvicorn running on http://0.0.0.0:8000
# [implementor]  Implementor worker started — waiting for tasks
# [reviewer]     Reviewer worker started — waiting for tasks
```

### 6. Probar

Abrir un issue en `factory-demo` con:
- Title: `Bug: divide function crashes on zero division`
- Body: `The divide() function raises ZeroDivisionError instead of a proper ValueError. It should raise ValueError("Cannot divide by zero").`

O usar el script de simulación local:
```bash
python scripts/simulate_issue.py \
  --repo TU_USER/factory-demo \
  --title "Bug: divide function crashes on zero division" \
  --body "The divide() function raises ZeroDivisionError. Should raise ValueError('Cannot divide by zero')."
```

En ~2-4 minutos deberías ver un PR abierto automáticamente.

---

## Setup en cloud (3 VMs en AWS)

### 1. Preparar variables

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars con tus valores
```

Crear `infra/terraform.tfvars`:
```hcl
key_name              = "mi-keypair"
admin_cidr            = "MI_IP/32"
redis_password        = "password-seguro-aqui"
anthropic_api_key     = "sk-ant-..."
github_token          = "ghp_..."
github_webhook_secret = "mi-webhook-secret"
```

### 2. Actualizar el repo en setup.sh

En `infra/scripts/setup.sh`, reemplazar:
```bash
git clone https://github.com/YOUR_ORG/YOUR_FACTORY_REPO /opt/factory
```
por la URL de tu fork de este repositorio.

### 3. Deploy

```bash
cd infra
terraform init
terraform apply
```

El output incluye:
```
webhook_url = "http://1.2.3.4:8000/webhook"
```

Pegar esa URL en el webhook de GitHub.

### 4. Verificar

```bash
ssh ubuntu@<orchestrator_ip> "docker compose logs orchestrator"
ssh ubuntu@<implementor_ip> "docker compose logs implementor"
ssh ubuntu@<reviewer_ip> "docker compose logs reviewer"
```

---

## Flujo de un issue

### Issue simple (sin spec)
```
Issue abierto
→ [~5s]   Triage: automatable=true, complexity=low, needs_spec=false
→ [~10s]  Comentario: "Implementación iniciada, branch: factory/abc123/issue-42"
→ [~2min] Implementor: clona repo, escribe fix, corre tests
→ [~3min] Comentario: "✅ Implementación lista. Enviando a revisión."
→ [~4min] Reviewer: code review + verifica tests en entorno limpio
→ [~4min] PR abierto: "fix: divide function crashes on zero division (closes #42)"
→ Notificación al dev → review → merge
```

### Issue complejo (con spec)
```
Issue abierto
→ Triage: automatable=true, complexity=high, needs_spec=true
→ Spec generado y comentado en el issue
→ [Human] responde "/factory approve" en GitHub
→ Implementación inicia normalmente...
```

---

## Extender el factory

El diseño es modular. Algunas extensiones:

**Monitor agent** (módulo 12): corre cada hora, analiza métricas/errores en producción, abre issues automáticamente si detecta anomalías.

**Parallelismo**: escalar VM2 horizontalmente — más workers leyendo del mismo queue de Redis para procesar múltiples issues en simultáneo.

**Slack integration**: el orchestrator puede notificar en Slack además de GitHub cuando un PR está listo.

**Evals del factory** (módulo 10): medir qué porcentaje de issues se resuelven correctamente en el primer intento, y usar esos datos para mejorar los system prompts.

---

Ver [EXAMPLES.md](./EXAMPLES.md) para un trace completo con outputs reales.
