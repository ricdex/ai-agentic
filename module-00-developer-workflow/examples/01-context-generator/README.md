# 01 — Context Generator

**Cuándo usarlo:** proyecto existente que no tiene `CONTEXT.md`. Uso único (retrofit).

**Cuándo NO usarlo:** proyecto nuevo. En proyectos nuevos el `CONTEXT.md` se escribe antes que el código — es el diseño del dominio, no una descripción de lo que ya existe.

## Qué hace

El agente lee el codebase, identifica entidades, reglas de negocio y patrones de código,
y genera un `CONTEXT.md` borrador. Vos lo revisás y ajustás — el AI puede inferir el "qué"
pero no siempre entiende el "por qué" detrás de las decisiones.

## Correr con el sample-repo incluido

```bash
cd examples/01-context-generator
export ANTHROPIC_API_KEY="sk-ant-..."
python context_generator.py
# Output: sample-repo/CONTEXT.md
```

## Correr con tu propio repo

```bash
python context_generator.py /ruta/a/tu/repo
```

## El sample-repo

Codebase de e-commerce mínima con tres módulos:
- `src/orders.py` — `Order`, `OrderItem`, `OrderStatus` con máquina de estados
- `src/payments.py` — `PaymentProcessor` como adaptador sobre proveedores externos
- `src/notifications.py` — `NotificationService` desacoplada del dominio

Es el mismo dominio que usan los ejemplos 02 al 06 — podés comparar el `CONTEXT.md`
generado con el `CONTEXT.md` escrito a mano en `02-grill-before-code/`.
