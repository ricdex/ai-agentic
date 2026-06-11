# ADR 001: Congelar el precio del Order al confirmar

**Estado:** Aceptado
**Fecha:** 2025-03-10

## Contexto

El catálogo de productos puede cambiar de precio en cualquier momento.
Sin una estrategia explícita, el total de un Order podría variar entre
el momento de creación y el de procesamiento del pago.

Dos opciones consideradas:
1. Calcular el total siempre desde el catálogo en vivo
2. Congelar el precio al confirmar el Order

## Decisión

Congelamos el precio total en `Order.confirmed_price` al llamar `confirm()`.
A partir de ese momento, `Order.total` retorna `confirmed_price`, ignorando
cambios posteriores en el catálogo.

## Consecuencias

**Positivas:**
- El precio que ve el cliente es exactamente lo que se le cobra
- Sin sorpresas entre "agregar al carrito" y "pagar"
- Auditoría simple: el Order tiene el precio histórico registrado

**Negativas:**
- Si el precio baja después de confirmar, el cliente no se beneficia automáticamente
- Requiere reconfirmar el Order si el cliente quiere el precio actualizado (no implementado)

## Impacto en el código

- `Order.confirm()` debe setear `confirmed_price = self.total` antes de cambiar el estado
- `Order.total` debe retornar `confirmed_price` si no es `None`
- Los tests deben verificar que cambios post-confirmación no alteran el total
