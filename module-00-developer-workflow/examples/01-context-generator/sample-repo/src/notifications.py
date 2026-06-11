from dataclasses import dataclass
from enum import Enum
from .orders import Order, OrderStatus


class NotificationChannel(Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


@dataclass
class NotificationResult:
    sent: bool
    channel: NotificationChannel
    recipient: str
    error: str | None = None


class NotificationService:
    """
    Envía notificaciones al cliente cuando cambia el estado de un Order.
    Desacoplado del dominio: Order no sabe que existe NotificationService.
    """

    STATUS_MESSAGES = {
        OrderStatus.CONFIRMED: "Tu pedido fue confirmado y está siendo preparado.",
        OrderStatus.SHIPPED:   "Tu pedido está en camino. Código de seguimiento: {tracking}",
        OrderStatus.DELIVERED: "Tu pedido fue entregado. ¡Gracias por tu compra!",
        OrderStatus.CANCELLED: "Tu pedido fue cancelado. Motivo: {reason}",
    }

    def __init__(self, email_client, sms_client=None):
        self._email = email_client
        self._sms = sms_client

    def notify_status_change(self, order: Order, customer_email: str) -> list[NotificationResult]:
        message_template = self.STATUS_MESSAGES.get(order.status)
        if not message_template:
            return []  # no hay notificación para este estado

        message = message_template.format(
            tracking=order.tracking_code or "",
            reason=order.cancellation_reason or ""
        )

        results = []

        # Email siempre
        try:
            self._email.send(
                to=customer_email,
                subject=f"Pedido #{order.id} — {order.status.value}",
                body=message
            )
            results.append(NotificationResult(
                sent=True, channel=NotificationChannel.EMAIL, recipient=customer_email
            ))
        except Exception as e:
            results.append(NotificationResult(
                sent=False, channel=NotificationChannel.EMAIL,
                recipient=customer_email, error=str(e)
            ))

        return results
