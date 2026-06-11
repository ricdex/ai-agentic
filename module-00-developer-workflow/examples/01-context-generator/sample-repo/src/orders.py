from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class OrderItem:
    product_id: str
    quantity: int
    unit_price: float

    @property
    def subtotal(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class Order:
    id: str
    customer_id: str
    items: list[OrderItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    # El precio se congela al confirmar — no fluctúa con el catálogo
    confirmed_price: float | None = None
    tracking_code: str | None = None
    cancellation_reason: str | None = None

    @property
    def total(self) -> float:
        if self.confirmed_price is not None:
            return self.confirmed_price
        return sum(item.subtotal for item in self.items)

    def confirm(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"Solo se puede confirmar un Order en PENDING, está en {self.status.value}")
        if not self.items:
            raise ValueError("No se puede confirmar un Order sin items")
        self.confirmed_price = self.total  # congelar precio
        self.status = OrderStatus.CONFIRMED

    def ship(self, tracking_code: str) -> None:
        if self.status != OrderStatus.CONFIRMED:
            raise ValueError(f"Solo se puede enviar un Order CONFIRMED, está en {self.status.value}")
        if not tracking_code:
            raise ValueError("tracking_code requerido para enviar")
        self.tracking_code = tracking_code
        self.status = OrderStatus.SHIPPED

    def deliver(self) -> None:
        if self.status != OrderStatus.SHIPPED:
            raise ValueError(f"Solo se puede entregar un Order SHIPPED, está en {self.status.value}")
        self.status = OrderStatus.DELIVERED

    def cancel(self, reason: str) -> None:
        if self.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise ValueError(f"No se puede cancelar un Order en estado {self.status.value}")
        if not reason:
            raise ValueError("Se requiere motivo de cancelación")
        self.cancellation_reason = reason
        self.status = OrderStatus.CANCELLED
