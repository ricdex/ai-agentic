# Onboarding

Este repositorio enseña AI Engineering con un principio operativo: la especificación define el resultado; el agente escribe solo el código mínimo para verificarlo.

## Primer recorrido

1. Lee el `README.md` y empieza por `module-00-developer-workflow`.
2. Crea una copia de `module-00-developer-workflow/templates/feature-spec.md.template` antes de pedir una implementación no trivial.
3. Define resultado, alcance, reglas y criterios de aceptación.
4. Convierte los comportamientos críticos en tests y, si interviene un LLM, en evals con un umbral explícito.
5. Deja que el agente implemente; revisa el diff contra la spec, no por cantidad de código.

## Qué se espera de un AI Engineer

- Traducir necesidades de negocio a contratos verificables.
- Elegir el workflow más simple que satisface el contrato.
- Definir permisos, límites de coste, fallback y revisión humana antes de automatizar acciones.
- Mantener evals, trazas y decisiones como artefactos de producción.
