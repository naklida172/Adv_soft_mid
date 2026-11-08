import hmac
import hashlib
import json
import httpx
from datetime import datetime, timezone
from typing import Optional

from app.models.schemas import PaymentResponse
from app.core.logger import logger


class WebhookNotificationService:
    """
    Сервис отправки асинхронных уведомлений (Webhooks) вызывающим сервисам
    с цифровой подписью HMAC SHA-256 для защиты от подделки.
    """

    def __init__(self, secret_key: str = "payment-gateway-webhook-secret"):
        self.secret_key = secret_key

    def generate_signature(self, payload_json: str) -> str:
        return hmac.new(
            self.secret_key.encode("utf-8"),
            payload_json.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    async def send_payment_callback(self, callback_url: str, payment: PaymentResponse, timeout_sec: float = 5.0) -> bool:
        if not callback_url:
            return False

        payload_dict = payment.model_dump(mode="json")
        payload_json = json.dumps(payload_dict, sort_keys=True)
        signature = self.generate_signature(payload_json)

        headers = {
            "Content-Type": "application/json",
            "X-Gateway-Signature": signature,
            "X-Gateway-Timestamp": datetime.now(timezone.utc).isoformat(),
            "User-Agent": "CryptoPaymentGateway-Webhook/1.0"
        }

        logger.info(f"Отправка Webhook уведомления для заказа {payment.order_id} на {callback_url}...")
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                res = await client.post(callback_url, content=payload_json, headers=headers)
                logger.info(f"Webhook на {callback_url} ответил со статусом: {res.status_code}")
                return 200 <= res.status_code < 300
        except Exception as e:
            logger.warning(f"Не удалось доставить Webhook на {callback_url}: {e}")
            return False


webhook_service = WebhookNotificationService()

