import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.orders import Order, OrderItem, OrderStatus


def make_order():
    return Order(
        id="ord-001",
        customer_id="cust-42",
        items=[OrderItem(product_id="prod-1", quantity=2, unit_price=25.0)]
    )


def test_confirm_pending_order():
    order = make_order()
    order.confirm()
    assert order.status == OrderStatus.CONFIRMED
    assert order.confirmed_price == 50.0


def test_price_freezes_on_confirm():
    order = make_order()
    order.confirm()
    order.items[0].unit_price = 999.0  # cambio posterior no afecta
    assert order.total == 50.0


def test_cannot_confirm_twice():
    order = make_order()
    order.confirm()
    with pytest.raises(ValueError):
        order.confirm()


def test_ship_confirmed_order():
    order = make_order()
    order.confirm()
    order.ship("TRACK-123")
    assert order.status == OrderStatus.SHIPPED
    assert order.tracking_code == "TRACK-123"


def test_cancel_pending_order():
    order = make_order()
    order.cancel("Cliente se arrepintió")
    assert order.status == OrderStatus.CANCELLED


def test_cannot_cancel_shipped_order():
    order = make_order()
    order.confirm()
    order.ship("TRACK-123")
    with pytest.raises(ValueError):
        order.cancel("tarde")
