import pytest
from decimal import Decimal
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.schemas import PaymentStatus, StepName, StepStatus
from app.providers.factory import WalletProviderFactory
from app.providers.mock_provider import MockWalletProvider


@pytest.fixture(autouse=True)
def setup_mock_provider():
    """Сбрасываем мок-провайдер перед тестами с нулевой задержкой для скорости."""
    mock_prov = MockWalletProvider(latency_ms=0)
    WalletProviderFactory.set_provider(mock_prov)
    yield mock_prov


@pytest.mark.asyncio
async def test_successful_payment_all_steps():
    """
    Тест полного успешного сценария:
    1. Проверка клиента в кошельке -> SUCCESS
    2. Запрос на данные кошелька -> SUCCESS
    3. Повторный запрос на чек баланса -> SUCCESS
    4. Исполнение и возврат ответа -> APPROVED
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_data = {
            "service_id": "shop_service_main",
            "order_id": "ord_10001",
            "client_id": "client_rich_01",
            "amount": "150.00",
            "currency": "USDT",
            "description": "Покупка премиум-подписки"
        }
        res = await client.post("/api/v1/payments/process", json=req_data)
        assert res.status_code == 200
        data = res.json()

        assert data["is_success"] is True
        assert data["status"] == PaymentStatus.APPROVED
        assert data["client_id"] == "client_rich_01"
        assert Decimal(str(data["amount"])) == Decimal("150.00")
        assert data["transaction_hash"] is not None
        assert data["transaction_hash"].startswith("0x")

        # Проверяем все 4 этапа в протоколе шагов
        steps = data["steps"]
        assert len(steps) == 4

        # Шаг 1: Проверка клиента в кошельке
        assert steps[0]["step"] == StepName.VERIFY_CLIENT
        assert steps[0]["status"] == StepStatus.SUCCESS

        # Шаг 2: Запрос метаданных кошелька
        assert steps[1]["step"] == StepName.GET_WALLET_DATA
        assert steps[1]["status"] == StepStatus.SUCCESS
        assert "network" in steps[1]["data"]

        # Шаг 3: Повторный запрос на чек баланса
        assert steps[2]["step"] == StepName.CHECK_BALANCE
        assert steps[2]["status"] == StepStatus.SUCCESS
        assert Decimal(steps[2]["data"]["available_balance"]) >= Decimal("150.00")

        # Шаг 4: Выполнение списания
        assert steps[3]["step"] == StepName.EXECUTE_PAYMENT
        assert steps[3]["status"] == StepStatus.SUCCESS


@pytest.mark.asyncio
async def test_rejection_at_step1_unknown_client():
    """
    Тест отклонения на Шаге 1: клиент отсутствует в кошельке.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_data = {
            "service_id": "billing_service",
            "order_id": "ord_unknown_01",
            "client_id": "non_existent_client_999",
            "amount": "50.00",
            "currency": "USDT"
        }
        res = await client.post("/api/v1/payments/process", json=req_data)
        assert res.status_code == 200
        data = res.json()

        assert data["is_success"] is False
        assert data["status"] == PaymentStatus.REJECTED
        assert "не зарегистрирован" in data["failure_reason"]

        # Шаг 1 завершился ошибкой, последующие шаги не выполнялись
        assert len(data["steps"]) == 1
        assert data["steps"][0]["step"] == StepName.VERIFY_CLIENT
        assert data["steps"][0]["status"] == StepStatus.FAILED


@pytest.mark.asyncio
async def test_rejection_at_step1_blocked_client():
    """
    Тест отклонения на Шаге 1: клиент заблокирован в кошельке.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_data = {
            "service_id": "shop_service",
            "order_id": "ord_blocked_01",
            "client_id": "client_blocked_03",
            "amount": "10.00",
            "currency": "USDT"
        }
        res = await client.post("/api/v1/payments/process", json=req_data)
        assert res.status_code == 200
        data = res.json()

        assert data["is_success"] is False
        assert data["status"] == PaymentStatus.REJECTED
        assert "заблокирован" in data["failure_reason"]
        assert len(data["steps"]) == 1
        assert data["steps"][0]["status"] == StepStatus.FAILED


@pytest.mark.asyncio
async def test_rejection_at_step3_insufficient_funds():
    """
    Тест отклонения на Шаге 3 (Повторный чек баланса):
    Шаг 1 и 2 пройдены успешно, но средств на счете клиента недостаточно.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # У client_poor_02 баланс всего 15 USDT, запрашиваем 500 USDT
        req_data = {
            "service_id": "game_service",
            "order_id": "ord_poor_01",
            "client_id": "client_poor_02",
            "amount": "500.00",
            "currency": "USDT"
        }
        res = await client.post("/api/v1/payments/process", json=req_data)
        assert res.status_code == 200
        data = res.json()

        assert data["is_success"] is False
        assert data["status"] == PaymentStatus.REJECTED
        assert "Недостаточно средств" in data["failure_reason"]

        steps = data["steps"]
        assert len(steps) == 3
        # Шаг 1 прошел
        assert steps[0]["step"] == StepName.VERIFY_CLIENT
        assert steps[0]["status"] == StepStatus.SUCCESS
        # Шаг 2 прошел
        assert steps[1]["step"] == StepName.GET_WALLET_DATA
        assert steps[1]["status"] == StepStatus.SUCCESS
        # Шаг 3 упал по нехватке средств
        assert steps[2]["step"] == StepName.CHECK_BALANCE
        assert steps[2]["status"] == StepStatus.FAILED


@pytest.mark.asyncio
async def test_idempotency_order_id():
    """
    Тест идемпотентности: повторный вызов с тем же order_id возвращает кэшированный результат.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_data = {
            "service_id": "crm_service",
            "order_id": "ord_idempotent_123",
            "client_id": "client_rich_01",
            "amount": "100.00",
            "currency": "USDT"
        }
        res1 = await client.post("/api/v1/payments/process", json=req_data)
        res2 = await client.post("/api/v1/payments/process", json=req_data)

        assert res1.json()["payment_id"] == res2.json()["payment_id"]
        assert res1.json()["transaction_hash"] == res2.json()["transaction_hash"]


@pytest.mark.asyncio
async def test_health_check_endpoint():
    """
    Тест проверки здоровья сервиса и криптопровайдера.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["wallet_node_connected"] is True

