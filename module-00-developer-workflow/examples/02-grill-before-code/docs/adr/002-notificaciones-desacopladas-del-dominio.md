# ADR 002: Notificaciones desacopladas del dominio de Order

**Estado:** Aceptado
**Fecha:** 2025-04-02

## Contexto

Cuando un Order cambia de estado, el cliente debe recibir una notificación.
La pregunta es: ¿quién es responsable de enviarla?

Opciones consideradas:
1. `Order.confirm()` llama directamente al `NotificationService`
2. El caso de uso (service layer) llama al `NotificationService` después de modificar el Order
3. Eventos de dominio: `Order` emite un evento, un listener notifica

## Decisión

Opción 2: el caso de uso orquesta el dominio y la notificación por separado.
`Order` no sabe que existe `NotificationService`.

No usamos eventos de dominio todavía — la complejidad no está justificada
con un solo subscriber por evento.

## Consecuencias

**Positivas:**
- `Order` es testeable sin mocks de infraestructura
- Cambiar el canal de notificación (email → push) no toca el dominio
- El flujo es legible en el caso de uso: `order.confirm() → notify()`

**Negativas:**
- El desarrollador puede olvidar llamar a `notify()` después de cambiar el estado
- Si se agrega un segundo lugar donde se confirma un Order, hay que recordar notificar ahí también

## Nota para el agente

Si una feature necesita enviar notificaciones al modificar un Order, el código
de notificación va en el caso de uso, **no** en el domain object.
