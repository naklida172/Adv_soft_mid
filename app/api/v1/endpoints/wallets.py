from decimal import Decimal
from typing import Optional, Dict
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException

from app.models.schemas import (
    ClientVerificationResult,
    WalletDataResult,
    BalanceCheckResult
)
from app.providers.base import BaseWalletProvider
from app.providers.mock_provider import MockWalletProvider, MockWalletAccount
from app.api.deps import get_wallet_provider, verify_service_api_key

router = APIRouter(prefix="/wallets", tags=["Кошельки (Wallets & Clients)"])


class VerifyClientRequest(BaseModel):
    client_id: str = Field(..., description="ID клиента или публичный крипто-адрес")
    currency: str = Field(default="USDT")


class SeedWalletRequest(BaseModel):
    client_id: str
    address: str
    balances: Dict[str, Decimal] = {"USDT": Decimal("1000.00")}
    is_active: bool = True
    is_blocked: bool = False
    network: str = "Ethereum/Polygon"


@router.post(
    "/verify-client",
    response_model=ClientVerificationResult,
    summary="Шаг 1 (Автономно): Проверить существование и статус клиента в кошельке"
)
async def verify_client(
    req: VerifyClientRequest,
    provider: BaseWalletProvider = Depends(get_wallet_provider),
    api_key: Optional[str] = Depends(verify_service_api_key)
) -> ClientVerificationResult:
    return await provider.verify_client(req.client_id, req.currency)


@router.get(
    "/{client_id_or_address}/data",
    response_model=WalletDataResult,
    summary="Шаг 2 (Автономно): Получить метаданные кошелька и оценку комиссии"
)
async def get_wallet_data(
    client_id_or_address: str,
    currency: str = Query(default="USDT"),
    provider: BaseWalletProvider = Depends(get_wallet_provider),
    api_key: Optional[str] = Depends(verify_service_api_key)
) -> WalletDataResult:
    return await provider.get_wallet_data(client_id_or_address, currency)


@router.get(
    "/{client_id_or_address}/balance",
    response_model=BalanceCheckResult,
    summary="Шаг 3 (Автономно): Проверить баланс клиента в кошельке"
)
async def check_balance(
    client_id_or_address: str,
    amount: Decimal = Query(..., gt=0, description="Требуемая сумма для проверки"),
    currency: str = Query(default="USDT"),
    provider: BaseWalletProvider = Depends(get_wallet_provider),
    api_key: Optional[str] = Depends(verify_service_api_key)
) -> BalanceCheckResult:
    return await provider.check_balance(client_id_or_address, currency, amount)


@router.post(
    "/mock/seed",
    summary="Добавить тестовый кошелек в Mock-провайдер (для интеграционных тестов)"
)
async def seed_mock_wallet(
    req: SeedWalletRequest,
    provider: BaseWalletProvider = Depends(get_wallet_provider),
    api_key: Optional[str] = Depends(verify_service_api_key)
):
    if not isinstance(provider, MockWalletProvider):
        raise HTTPException(
            status_code=400,
            detail="Динамическое добавление кошельков доступно только в MockWalletProvider."
        )

    acc = MockWalletAccount(
        client_id=req.client_id,
        address=req.address,
        balances=req.balances,
        is_active=req.is_active,
        is_blocked=req.is_blocked,
        network=req.network
    )
    provider.register_account(acc)
    return {"status": "ok", "message": f"Тестовый аккаунт {req.client_id} успешно зарегистрирован"}

