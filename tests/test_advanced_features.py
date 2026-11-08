import pytest
import json
from decimal import Decimal
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.storage import SQLitePaymentRepository
from app.services.webhook_service import WebhookNotificationService
from app.models.schemas import PaymentResponse, PaymentStatus, StepName, StepStatus, PipelineStepLog
from app.providers.factory import WalletProviderFactory
from app.providers.mock_provider import MockWalletProvider


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_payments.db"
    repo = SQLitePaymentRepository(db_path=str(db_file))
    return repo


@pytest.mark.asyncio
async def test_sqlite_repository_persistence(temp_db):
    """Проверка сохранения и извлечения платежа из SQLite базы данных."""
    step = PipelineStepLog(
        step=StepName.VERIFY_CLIENT,
        status=StepStatus.SUCCESS,
        message="Client verified ok"
    )
    payment = PaymentResponse(
        payment_id="pay_test_sql_001",
        order_id="order_sql_99",
        service_id="test_service",
        client_id="client_rich_01",
        amount=Decimal("199.99"),
        currency="USDT",
        status=PaymentStatus.APPROVED,
        is_success=True,
        transaction_hash="0xabcd1234",
        fee_estimated=Decimal("0.50"),
        steps=[step],
        created_at=pytest.importorskip("datetime").datetime.now(pytest.importorskip("datetime").timezone.utc)
    )

    await temp_db.save(payment)

    # Проверка получения по ID
    loaded = await temp_db.get_by_id("pay_test_sql_001")
    assert loaded is not None
    assert loaded.payment_id == "pay_test_sql_001"
    assert loaded.amount == Decimal("199.99")
    assert loaded.is_success is True
    assert len(loaded.steps) == 1
    assert loaded.steps[0].step == StepName.VERIFY_CLIENT

    # Проверка поиска по order_id
    by_order = await temp_db.get_by_order_id("test_service", "order_sql_99")
    assert by_order is not None
    assert by_order.payment_id == "pay_test_sql_001"


def test_webhook_hmac_signature():
    """Проверка генерации HMAC SHA-256 подписи вебхука."""
    service = WebhookNotificationService(secret_key="secret-key-123")
    payload = json.dumps({"order_id": "ORD-1", "status": "APPROVED"}, sort_keys=True)
    sig1 = service.generate_signature(payload)
    sig2 = service.generate_signature(payload)

    # Детерминированность подписи
    assert sig1 == sig2
    assert len(sig1) == 64  # Длина sha256 hex строки


@pytest.mark.asyncio
async def test_dashboard_endpoint_html():
    """Проверка доступности визуального дашборда."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/dashboard")
        assert res.status_code == 200
        assert "Payment Gateway" in res.text
        assert "text/html" in res.headers["content-type"]

