# 00 — Project Init

Generador de archivos de contexto AI-first. Genera **un archivo por ejecución**.

## Reglas de dependencia

```
CONTEXT.md   → se puede generar siempre (es la base)
CLAUDE.md    → requiere CONTEXT.md
ADR          → requiere CONTEXT.md + CLAUDE.md
```

Si intentás generar CLAUDE.md sin CONTEXT.md, el menú lo muestra deshabilitado.

## Backup automático

Si CONTEXT.md (o CLAUDE.md) ya existe y elegís generarlo de nuevo, el archivo anterior
se mueve a `_backups/CONTEXT.md.20240610_143022.bak` antes de escribir el nuevo.

## Validación de contradicciones

Antes de escribir, el agente lee los archivos existentes y verifica que el nuevo contenido
no los contradiga. Si encuentra conflictos, los muestra y pregunta si continuar:

```
  ⚠  Se encontraron 1 contradicción(es) con archivos existentes:

  [CONFLICTO] CONTEXT.md
    Existente: El sistema es stateless — no almacena sesiones
    Propuesto: Usamos Redis para sesiones de usuario

  ¿Continuar igual? (s = sí / n = cancelar):
```

Los conflictos tienen dos severidades:
- `hard` — incompatibilidad directa (una dice blanco, la otra negro)
- `soft` — tensión o ambigüedad que vale la pena revisar

## Correr

```bash
cd examples/00-project-init
export ANTHROPIC_API_KEY="sk-ant-..."

# En el directorio actual:
python project_init.py

# Apuntando a tu proyecto:
python project_init.py --output /ruta/a/mi-proyecto
```

## Flujo de una sesión nueva (sin ningún archivo)

```
python project_init.py

Estado actual:
  ✗ CONTEXT.md
  ✗ CLAUDE.md
  ✗ docs/adr/   (sin ADRs)

¿Qué querés generar?

  1. CONTEXT.md — dominio, entidades, reglas de negocio
  2. CLAUDE.md  (requiere CONTEXT.md primero)
  3. ADR        (requiere CONTEXT.md + CLAUDE.md primero)

  q. Salir
```

**Corrés 1** → el agente te hace preguntas de dominio → escribe CONTEXT.md

**Volvés a correr** → ahora el 2 está habilitado → preguntas de stack → CLAUDE.md

**Volvés a correr** → ahora el 3 está habilitado → pregunta por la decisión → ADR

## Qué genera cada modo

### 1 — CONTEXT.md

Preguntas típicas:
- ¿Qué hace este sistema en una oración?
- ¿Cuáles son las entidades principales y qué reglas tienen?
- ¿Qué nunca debe poder pasar en este sistema?
- ¿Qué está explícitamente fuera del scope?

### 2 — CLAUDE.md

Preguntas típicas:
- ¿Qué lenguaje, framework y base de datos usás?
- ¿Cómo está organizado el código (carpetas, capas)?
- ¿Qué framework de tests usás? ¿Cómo se corre el linter?
- ¿Hay patrones que querés que el AI siempre siga o siempre evite?

### 3 — ADR

Preguntas típicas:
- ¿Qué decisión no obvia tomaron que cualquier dev nuevo podría querer cambiar?
- ¿Por qué esa decisión y no la alternativa más simple?
- ¿Qué se sacrificó conscientemente al tomar esa decisión?

## Qué sigue

Una vez que tenés los tres archivos:

```bash
python ../02-grill-before-code/grill_before_code.py "descripción de la primera feature"
```
