from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks

from app.models.schemas import PaymentInitiateRequest, PaymentResponse
from app.services.payment_service import PaymentProcessingService
from app.services.storage import PaymentRepository
from app.services.webhook_service import webhook_service
from app.api.deps import get_payment_service, get_payment_repository, verify_service_api_key

router = APIRouter(prefix="/payments", tags=["Платежи (Payments)"])


@router.post(
    "/process",
    response_model=PaymentResponse,
    summary="Провести оплату (Основной пайплайн)",
    description=(
        "Главный эндпоинт для внешних сервисов.\n\n"
        "Выполняет 4 обязательных шага:\n"
        "1. **Проверка клиента** в кошельке (существование, статус, отсутствие блокировок)\n"
        "2. **Запрос данных** кошелька (сеть, тип, комиссия gas/fee, nonce)\n"
        "3. **Повторный чек баланса** (проверка достаточности средств перед транзакцией)\n"
        "4. **Исполнение и ответ** (списание средств, формирование hash и возврат подробного отчета)"
    )
)
async def process_payment(
    request: PaymentInitiateRequest,
    background_tasks: BackgroundTasks,
    service: PaymentProcessingService = Depends(get_payment_service),
    api_key: Optional[str] = Depends(verify_service_api_key)
) -> PaymentResponse:
    response = await service.process_payment(request)
    
    # Если вызывающий сервис запросил вебхук, отправляем его асинхронно в фоне
    if request.callback_url:
        background_tasks.add_task(
            webhook_service.send_payment_callback,
            callback_url=request.callback_url,
            payment=response
        )

    return response


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Получить статус и аудит платежа по ID"
)
async def get_payment_by_id(
    payment_id: str,
    repo: PaymentRepository = Depends(get_payment_repository),
    api_key: Optional[str] = Depends(verify_service_api_key)
) -> PaymentResponse:
    payment = await repo.get_by_id(payment_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Платеж с ID '{payment_id}' не найден."
        )
    return payment


@router.get(
    "/order/{order_id}",
    response_model=PaymentResponse,
    summary="Получить платеж по Order ID вызывающего сервиса"
)
async def get_payment_by_order_id(
    order_id: str,
    service_id: str = Query(..., description="ID внешнего сервиса"),
    repo: PaymentRepository = Depends(get_payment_repository),
    api_key: Optional[str] = Depends(verify_service_api_key)
) -> PaymentResponse:
    payment = await repo.get_by_order_id(service_id, order_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Платеж для заказа '{order_id}' сервиса '{service_id}' не найден."
        )
    return payment


@router.get(
    "",
    response_model=List[PaymentResponse],
    summary="Список последних транзакций (Аудит / Мониторинг)"
)
async def list_payments(
    limit: int = Query(default=20, ge=1, le=100),
    repo: PaymentRepository = Depends(get_payment_repository),
    api_key: Optional[str] = Depends(verify_service_api_key)
) -> List[PaymentResponse]:
    return await repo.list_all(limit=limit)

