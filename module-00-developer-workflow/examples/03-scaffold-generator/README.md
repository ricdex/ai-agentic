# 03 — Scaffold Generator

**Cuándo usarlo:** primer feature de un proyecto nuevo — después del grill, antes del primer TDD.

**Cuándo NO usarlo:** proyectos con estructura existente, o features que solo tocan archivos que ya existen.

## Qué hace

Lee CONTEXT.md + CLAUDE.md + ADRs + el plan del grill, y genera el esqueleto del proyecto:

- Estructura de carpetas
- `pyproject.toml` o `requirements.txt` (según el stack del CLAUDE.md)
- `__init__.py` y archivos de config
- Interfaces/protocolos base que reflejan las entidades del CONTEXT.md
- `conftest.py` con fixtures comunes
- `.gitignore`

**Lo que NO genera:** lógica de negocio. Eso va en el ciclo TDD.

## Por qué es AI-first

Sin scaffold, el primer TDD genera la estructura on-the-fly y puede no respetar las
convenciones del CLAUDE.md. Con scaffold generator, el AI lee las convenciones del proyecto
y genera una estructura coherente antes de escribir una sola línea de lógica.

Además puede hacer hasta 3 preguntas de estructura (monorepo vs single package,
ORM preferences, etc.) antes de generar — no asume nada que no está en el contexto.

## Correr con los inputs de ejemplo

```bash
cd examples/03-scaffold-generator
export ANTHROPIC_API_KEY="sk-ant-..."

# Usa grill_plan.txt + busca CONTEXT.md/CLAUDE.md en directorios padre
# (encuentra los de 02-grill-before-code automáticamente)
python scaffold_generator.py --plan grill_plan.txt --output ./output/e-commerce
```

## Correr para tu propio proyecto

```bash
# Desde la raíz de tu proyecto (donde está tu CONTEXT.md):
python /ruta/a/scaffold_generator.py --plan ./plan-del-grill.txt --output .
```

## El input: grill_plan.txt

El plan que produce `02-grill-before-code/grill_before_code.py` al final de la sesión.
El archivo incluido es el plan para el sistema de cupones del dominio e-commerce.

## El output

```
output/e-commerce/
├── src/
│   ├── __init__.py
│   ├── coupons.py        ← interfaces/protocolos (sin lógica)
│   ├── orders.py         ← tipos base
│   └── ports.py          ← CouponRegistry protocol
├── tests/
│   ├── __init__.py
│   └── conftest.py       ← fixtures comunes
├── pyproject.toml
└── .gitignore
```

El contenido exacto depende del stack que tenés en CLAUDE.md y las respuestas a las
preguntas de estructura.
