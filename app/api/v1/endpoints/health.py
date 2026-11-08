from fastapi import APIRouter, Depends
from app.config import settings
from app.providers.base import BaseWalletProvider
from app.api.deps import get_wallet_provider

router = APIRouter(tags=["Система (System & Health)"])


@router.get("/health", summary="Проверка состояния сервиса и крипто-ноды")
async def health(provider: BaseWalletProvider = Depends(get_wallet_provider)):
    wallet_connected = await provider.health_check()
    return {
        "status": "healthy" if wallet_connected else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "active_wallet_provider": provider.provider_name,
        "wallet_node_connected": wallet_connected
    }

