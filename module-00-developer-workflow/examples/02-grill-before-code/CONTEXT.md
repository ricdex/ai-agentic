# CONTEXT.md — E-Commerce Core

## Qué hace este sistema

Gestiona el ciclo de vida completo de pedidos de e-commerce, desde la creación hasta
la entrega, incluyendo pagos y notificaciones al cliente.

## Conceptos clave del dominio

- **Order**: representa la intención de compra de un cliente. Contiene `OrderItem`s.
  Distinto de `Invoice` (que no existe todavía) y de `Cart` (estado pre-compra, fuera de este módulo).

- **OrderStatus**: `PENDING → CONFIRMED → SHIPPED → DELIVERED`. También puede cancelarse
  desde `PENDING` o `CONFIRMED`, pero no desde `SHIPPED` o `DELIVERED`.

- **OrderItem**: un producto con cantidad y precio unitario dentro de un Order.

- **confirmed_price**: el precio total del Order se congela al confirmarse.
  Los cambios posteriores en el catálogo no afectan el precio del Order ya confirmado.

- **Payment**: resultado de cobrar un Order. Está desacoplado del dominio de Order —
  Order no sabe que existe PaymentProcessor.

- **PaymentStatus**: `PENDING → CAPTURED → REFUNDED` o `FAILED`. Un Payment fallido
  no modifica el Order — el llamador decide si reintentar.

- **NotificationService**: envía emails (y opcionalmente SMS) cuando cambia el estado
  de un Order. No es parte del dominio — es infraestructura llamada desde los casos de uso.

## Reglas del dominio

- Un Order no puede modificarse si está en `SHIPPED`, `DELIVERED` o `CANCELLED`
- El precio de un Order se congela al confirmarse (ver `confirmed_price`)
- `cancel()` requiere siempre un `reason` no vacío
- Para enviar un Order se necesita un `tracking_code`
- Un Payment solo se puede refundir si está en `CAPTURED`

## Patrones de código

- Los domain objects (`Order`, `Payment`) no importan nada de infraestructura
- `PaymentProcessor` es un adaptador sobre el cliente del proveedor (Stripe, PayPal)
- Los errores de dominio son `ValueError` con mensajes explícitos
- Los handlers son thin: validan → llaman dominio → retornan respuesta

## Lo que NO hacemos aquí

- No hay lógica de negocio en los handlers HTTP
- No hay llamadas a base de datos desde los domain objects
- No hay referencias a Stripe/PayPal en el dominio — solo en `PaymentProcessor`
- No hay un concepto de `Cart` en este módulo (es responsabilidad del frontend)
