# Feature Spec: Software Factory serverless y spec-first

**Estado:** Aprobada como dirección de arquitectura
**Fecha:** 2026-09-03
**Owner:** Curso AI Agentic Engineering

## Resultado de negocio

Un desarrollador convierte una issue de GitHub en un PR revisable sin que el sistema infiera alcance crítico: toda implementación se basa en una Feature Spec aprobada y cada ejecución tiene trazabilidad, límites de permisos y recuperación ante fallos.

## Alcance

**Incluye:**

- Toda issue automatizable genera una Feature Spec y espera aprobación humana antes de implementar.
- El estado del workflow y sus mensajes son durables; los workers son efímeros e idempotentes.
- Producción usa webhook público mínimo, cola gestionada, almacenamiento de estado gestionado, secretos en secret manager y runners aislados.

**No incluye:**

- Merge automático de PRs.
- Acceso a producción o credenciales con privilegios de administración para el implementor.
- Sustituir la revisión humana por una puntuación de LLM.

## Contrato observable

| Caso | Dado | Cuando | Entonces |
|---|---|---|---|
| Issue automatizable | Issue nueva válida | Termina triage | Se publica una Feature Spec y no se crea código todavía |
| Aprobación | Spec pendiente | Maintainer comenta `/factory approve` | Se encola una única implementación idempotente |
| Rechazo | Spec pendiente | Maintainer comenta `/factory reject` | No se ejecuta implementación y el feedback queda registrado |
| Fallo de worker | Mensaje en proceso | Se supera el límite de reintentos | El mensaje llega a DLQ y se crea alerta con trace id |

## Arquitectura de producción objetivo

```text
GitHub webhook → API Gateway + Lambda (validación) → EventBridge/SQS
                                                ↓
                  Step Functions (estado, reintentos y gate humano)
                         ↓                 ↓
                 Lambda: triage       Job efímero: implementor/reviewer
                         ↓                 ↓
                 DynamoDB/S3 traces   sandbox con credenciales de mínimo privilegio
```

La implementación actual con Docker Compose se conserva como laboratorio local. La infraestructura EC2 existente es una referencia heredada para el curso, no la arquitectura objetivo de producción.

## Criterios de aceptación

- [x] Ninguna issue automatizable llega al implementor sin Feature Spec aprobada.
- [ ] El despliegue cloud no requiere SSH, hosts persistentes ni Redis autogestionado.
- [ ] Cada transición tiene idempotency key, trace id, timeout, retry y ruta a DLQ.
- [ ] Los secretos se recuperan en runtime desde un secret manager y no pasan por Terraform state.
- [ ] La suite de evals bloquea promoción si baja la tasa de aprobación o aumenta el coste por issue sobre el umbral acordado.

## Plan de verificación

- **Tests deterministas:** firma del webhook, deduplicación, transición de estado, aprobación/rechazo y entrega a DLQ.
- **Evals:** conjunto versionado de issues simples, ambiguas y no automatizables; medir exactitud de triage, completitud de la spec, tasa de PR aceptados y coste por issue.
- **Observabilidad:** trace por task, métricas de cola/DLQ, tiempo hasta aprobación, ratio de reintentos y ratio de PR aceptados.
