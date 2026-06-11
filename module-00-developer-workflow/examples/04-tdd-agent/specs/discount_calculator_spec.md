# Spec: DiscountCalculator

Implementar una clase `DiscountCalculator` con las siguientes reglas:

## Comportamiento esperado

- `apply(price, discount_pct)`:
  - Retorna el precio con el descuento aplicado, redondeado a 2 decimales
  - Si `discount_pct` es `None` o `0`, retorna `price` sin cambios
  - Lanza `ValueError` si `price <= 0`
  - Lanza `ValueError` si `discount_pct` es negativo o mayor a 100

- `apply_coupon(price, coupon_code, coupon_registry)`:
  - `coupon_registry` es un dict `{code: discount_pct}`
  - Retorna el precio con descuento si el cupón es válido
  - Retorna `price` sin cambios si el cupón no existe (no lanza excepción)

- `bulk_discount(items)`:
  - `items`: lista de dicts `{"price": float, "quantity": int}`
  - Si la cantidad total es >= 10: aplica 5% de descuento sobre el total
  - Si la cantidad total es < 10: retorna el total sin descuento
  - Lanza `ValueError` si `items` está vacío
