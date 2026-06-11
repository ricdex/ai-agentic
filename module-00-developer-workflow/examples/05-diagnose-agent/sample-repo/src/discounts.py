# Módulo de descuentos — tiene bugs intencionales para el ejercicio de diagnóstico

def calculate_discount(price: float, discount_pct: float) -> float:
    """Calcula el precio con descuento aplicado."""
    discounted = price * (1 - discount_pct / 100)  # bug: falla si discount_pct es None
    return round(discounted, 2)


def apply_coupon(cart_total: float, coupon_code: str, valid_coupons: dict) -> float:
    """Aplica un cupón de descuento al total del carrito."""
    coupon = valid_coupons[coupon_code]  # bug: KeyError si el cupón no existe
    return calculate_discount(cart_total, coupon["discount_pct"])


def bulk_discount(items: list[dict]) -> float:
    """
    Calcula descuento por volumen.
    items: lista de dicts con 'price' y 'quantity'
    Regla: más de 10 unidades totales → 5% de descuento sobre el total
    """
    total = sum(item["price"] * item["quantity"] for item in items)
    total_units = sum(item["quantity"] for item in items)

    if total_units > 10:
        return total * 0.95
    return total  # bug: no aplica descuento cuando total_units == 10 (debería ser >= 10)
