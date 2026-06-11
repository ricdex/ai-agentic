import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.discounts import calculate_discount, apply_coupon, bulk_discount


def test_calculate_discount_basic():
    assert calculate_discount(100.0, 20) == 80.0


def test_calculate_discount_zero_pct():
    assert calculate_discount(50.0, 0) == 50.0


def test_calculate_discount_none_means_no_discount():
    # Cuando discount_pct es None, el producto no tiene descuento → precio original
    assert calculate_discount(100.0, None) == 100.0


def test_apply_coupon_valid():
    coupons = {"SAVE10": {"discount_pct": 10}}
    assert apply_coupon(100.0, "SAVE10", coupons) == 90.0


def test_apply_coupon_invalid_returns_none():
    coupons = {"SAVE10": {"discount_pct": 10}}
    result = apply_coupon(100.0, "INVALID", coupons)
    assert result is None  # cupón inválido → sin descuento, no excepción


def test_bulk_discount_above_threshold():
    items = [{"price": 10.0, "quantity": 6}, {"price": 5.0, "quantity": 6}]
    assert bulk_discount(items) == pytest.approx(99.0)  # 110 * 0.95


def test_bulk_discount_at_threshold():
    # exactamente 10 unidades → debe aplicar descuento también
    items = [{"price": 10.0, "quantity": 10}]
    assert bulk_discount(items) == pytest.approx(95.0)  # 100 * 0.95


def test_bulk_discount_below_threshold():
    items = [{"price": 10.0, "quantity": 5}]
    assert bulk_discount(items) == 50.0  # sin descuento
