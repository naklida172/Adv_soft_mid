from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from app.models.schemas import (
    ClientVerificationResult,
    WalletDataResult,
    BalanceCheckResult,
    TransferExecutionResult
)


class BaseWalletProvider(ABC):
    """
    Абстрактный базовый интерфейс (Port / SPI) для взаимодействия с любым
    open source криптокошельком или блокчейн-нодой.
    Любой кошелек (Bitcoin Core, Electrum, Web3/EVM, BTCPay Server и т.д.)
    реализует данный контракт.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Название провайдера / адаптера."""
        pass

    @abstractmethod
    async def verify_client(self, client_id_or_address: str, currency: str) -> ClientVerificationResult:
        """
        ШАГ 1: Проверка клиента в кошельке.
        Проверяет существование клиента/кошелька, статус активности,
        валидность крипто-адреса и отсутствие блокировок/ограничений.
        """
        pass

    @abstractmethod
    async def get_wallet_data(self, client_id_or_address: str, currency: str) -> WalletDataResult:
        """
        ШАГ 2: Запрос на данные кошелька.
        Получает метаданные кошелька (сеть, тип адреса, оценку сетевой комиссии / gas fee, nonce и т.д.).
        """
        pass

    @abstractmethod
    async def check_balance(
        self,
        client_id_or_address: str,
        currency: str,
        required_amount: Decimal
    ) -> BalanceCheckResult:
        """
        ШАГ 3: Повторный запрос на чек баланса клиента.
        Проверяет актуальный доступный баланс кошелька непосредственно перед списанием
        (с учетом суммы и комиссии).
        """
        pass

    @abstractmethod
    async def execute_transfer(
        self,
        client_id_or_address: str,
        currency: str,
        amount: Decimal,
        order_id: str
    ) -> TransferExecutionResult:
        """
        ШАГ 4: Списание / проведение транзакции.
        Генерирует и подписывает транзакцию (или регистрирует трансфер) и возвращает hash.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Проверка связи с кошельком / нодой."""
        pass

