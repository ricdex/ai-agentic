from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PaymentStatus(Enum):
    PENDING = "pending"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass
class Payment:
    id: str
    order_id: str
    amount: float
    provider: str  # "stripe" | "paypal"
    status: PaymentStatus = PaymentStatus.PENDING
    provider_reference: str | None = None
    failure_reason: str | None = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class PaymentProcessor:
    """
    Capa de abstracción sobre proveedores de pago.
    Los detalles del proveedor no deben filtrarse al dominio de Order.
    """

    def __init__(self, provider_client):
        self._client = provider_client

    def charge(self, order_id: str, amount: float, card_token: str) -> Payment:
        if amount <= 0:
            raise ValueError(f"amount debe ser positivo, recibido: {amount}")

        try:
            result = self._client.create_charge(
                amount=int(amount * 100),  # centavos
                source=card_token,
                metadata={"order_id": order_id}
            )
            return Payment(
                id=result["payment_id"],
                order_id=order_id,
                amount=amount,
                provider=self._client.name,
                status=PaymentStatus.CAPTURED,
                provider_reference=result["reference"]
            )
        except Exception as e:
            return Payment(
                id=f"failed_{order_id}",
                order_id=order_id,
                amount=amount,
                provider=self._client.name,
                status=PaymentStatus.FAILED,
                failure_reason=str(e)
            )

    def refund(self, payment: Payment) -> Payment:
        if payment.status != PaymentStatus.CAPTURED:
            raise ValueError(f"Solo se puede refundir un pago CAPTURED, está en {payment.status.value}")

        self._client.create_refund(payment.provider_reference)
        payment.status = PaymentStatus.REFUNDED
        return payment
