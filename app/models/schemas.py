from decimal import Decimal
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)



class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    VERIFYING = "VERIFYING"
    FETCHING_DATA = "FETCHING_DATA"
    CHECKING_BALANCE = "CHECKING_BALANCE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class StepName(str, Enum):
    VERIFY_CLIENT = "VERIFY_CLIENT"
    GET_WALLET_DATA = "GET_WALLET_DATA"
    CHECK_BALANCE = "CHECK_BALANCE"
    EXECUTE_PAYMENT = "EXECUTE_PAYMENT"


class StepStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PipelineStepLog(BaseModel):
    step: StepName
    status: StepStatus
    message: str
    timestamp: datetime = Field(default_factory=get_utc_now)
    data: Optional[Dict[str, Any]] = None


# --- Запросы и ответы от внешних сервисов ---

class PaymentInitiateRequest(BaseModel):
    """
    Запрос от внешнего микросервиса (магазина, биллинга, подсистемы).
    """
    service_id: str = Field(..., description="ID вызывающего сервиса (например, 'order_service_v2')")
    order_id: str = Field(..., description="Уникальный ID заказа в вызывающем сервисе")
    client_id: str = Field(..., description="ID клиента или публичный крипто-адрес кошелька")
    amount: Decimal = Field(..., gt=0, description="Сумма к списанию/оплате")
    currency: str = Field(default="USDT", description="Символ валюты/токена (USDT, USDC, BTC, ETH, TON)")
    description: Optional[str] = Field(default=None, description="Описание платежа")
    callback_url: Optional[str] = Field(default=None, description="URL для асинхронного вебхука (при необходимости)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Дополнительные метаданные заказа")


class PaymentResponse(BaseModel):
    """
    Итоговый ответ сервису. Содержит статус и полный отчет о пройденных проверках.
    """
    payment_id: str
    order_id: str
    service_id: str
    client_id: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    is_success: bool
    transaction_hash: Optional[str] = None
    fee_estimated: Optional[Decimal] = None
    failure_reason: Optional[str] = None
    steps: List[PipelineStepLog] = []
    created_at: datetime
    completed_at: Optional[datetime] = None


# --- Внутренние модели взаимодействия с Wallet Provider ---

class ClientVerificationResult(BaseModel):
    is_valid: bool
    exists: bool
    is_active: bool
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class WalletDataResult(BaseModel):
    network: str
    address: str
    wallet_type: str  # e.g., "HD_WALLET", "SMART_CONTRACT", "EVM_EOA", "BITCOIN_NATIVE_SEGWIT"
    estimated_fee: Decimal
    nonce: Optional[int] = None
    contract_address: Optional[str] = None
    extra_info: Optional[Dict[str, Any]] = None


class BalanceCheckResult(BaseModel):
    sufficient: bool
    available_balance: Decimal
    required_amount: Decimal
    currency: str
    details: Optional[Dict[str, Any]] = None


class TransferExecutionResult(BaseModel):
    success: bool
    tx_hash: Optional[str] = None
    error: Optional[str] = None
