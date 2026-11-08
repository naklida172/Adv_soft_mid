from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from app.config import settings
from app.providers.base import BaseWalletProvider
from app.providers.factory import WalletProviderFactory
from app.services.payment_service import PaymentProcessingService
from app.services.storage import PaymentRepository, payment_repo


async def verify_service_api_key(x_api_key: Optional[str] = Header(None)) -> Optional[str]:
    """
    Проверка подлинности вызывающего сервиса через заголовок X-API-Key.
    Если REQUIRE_API_KEY=False, проверка пропускается (для удобства локальной разработки).
    """
    if not settings.REQUIRE_API_KEY:
        return x_api_key or "anonymous-dev-service"

    if not x_api_key or x_api_key not in settings.SERVICE_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неавторизованный запрос: неверный или отсутствующий X-API-Key."
        )
    return x_api_key


def get_wallet_provider() -> BaseWalletProvider:
    return WalletProviderFactory.get_provider()


def get_payment_repository() -> PaymentRepository:
    return payment_repo


def get_payment_service(
    provider: BaseWalletProvider = Depends(get_wallet_provider),
    repo: PaymentRepository = Depends(get_payment_repository)
) -> PaymentProcessingService:
    return PaymentProcessingService(provider=provider, repository=repo)

