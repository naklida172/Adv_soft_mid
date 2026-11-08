import asyncio
import hashlib
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional

from app.providers.base import BaseWalletProvider
from app.models.schemas import (
    ClientVerificationResult,
    WalletDataResult,
    BalanceCheckResult,
    TransferExecutionResult
)
from app.core.logger import logger


class MockWalletAccount:
    def __init__(
        self,
        client_id: str,
        address: str,
        balances: Dict[str, Decimal],
        is_active: bool = True,
        is_blocked: bool = False,
        wallet_type: str = "OPEN_SOURCE_HD_WALLET",
        network: str = "POLYGON_MOCK"
    ):
        self.client_id = client_id
        self.address = address
        self.balances = balances  # { "USDT": Decimal("1000.00"), "BTC": Decimal("1.5") }
        self.is_active = is_active
        self.is_blocked = is_blocked
        self.wallet_type = wallet_type
        self.network = network
        self.nonce = 0


class MockWalletProvider(BaseWalletProvider):
    """
    Полноценный симулятор open-source криптокошелька.
    Имитирует ответы RPC-ноды с поддержкой различных сценариев:
    - Успешный платеж
    - Несуществующий клиент
    - Заблокированный кошелек
    - Недостаточный баланс на этапе повторной проверки
    """

    def __init__(self, latency_ms: int = 20):
        self._latency_ms = latency_ms
        self._accounts: Dict[str, MockWalletAccount] = {}
        self._init_default_demo_accounts()

    @property
    def provider_name(self) -> str:
        return "MockCryptoWalletProvider (Simulated Node)"

    def _init_default_demo_accounts(self):
        # 1. Богатый активный клиент (успешная оплата)
        self.register_account(
            MockWalletAccount(
                client_id="client_rich_01",
                address="0x71C8363837918a2130e947b19280145c2B9D45Ab",
                balances={
                    "USDT": Decimal("50000.00"),
                    "USDC": Decimal("25000.00"),
                    "ETH": Decimal("15.5"),
                    "BTC": Decimal("2.1")
                },
                network="Ethereum/Polygon"
            )
        )

        # 2. Клиент с маленьким балансом (отказ на шаге 3 "Чек баланса")
        self.register_account(
            MockWalletAccount(
                client_id="client_poor_02",
                address="0x1234567890123456789012345678901234567890",
                balances={
                    "USDT": Decimal("15.00"),
                    "BTC": Decimal("0.0001")
                },
                network="Polygon"
            )
        )

        # 3. Заблокированный клиент (отказ на шаге 1 "Проверка клиента")
        self.register_account(
            MockWalletAccount(
                client_id="client_blocked_03",
                address="0x9999999999999999999999999999999999999999",
                balances={"USDT": Decimal("100000.00")},
                is_blocked=True,
                network="Arbitrum"
            )
        )

        # 4. Bitcoin SegWit клиент
        self.register_account(
            MockWalletAccount(
                client_id="btc_client_04",
                address="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
                balances={"BTC": Decimal("0.85")},
                wallet_type="BITCOIN_ELECTRUM_CORE",
                network="Bitcoin_Mainnet"
            )
        )

    def register_account(self, account: MockWalletAccount):
        """Регистрирует аккаунт как по client_id, так и по публичному адресу."""
        self._accounts[account.client_id.lower()] = account
        self._accounts[account.address.lower()] = account

    def _find_account(self, client_id_or_address: str) -> Optional[MockWalletAccount]:
        key = client_id_or_address.strip().lower()
        if key in self._accounts:
            return self._accounts[key]
        
        # Если передан валидный адрес формата 0x... или bc1... и его нет в базе,
        # можем автоматически эмулировать динамический кошелек
        if key.startswith("0x") and len(key) == 42:
            auto_acc = MockWalletAccount(
                client_id=key,
                address=key,
                balances={"USDT": Decimal("1000.00"), "ETH": Decimal("2.0")},
                network="EVM_AutoDetected"
            )
            self.register_account(auto_acc)
            return auto_acc
        return None

    async def _simulate_rpc_call(self):
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

    async def verify_client(self, client_id_or_address: str, currency: str) -> ClientVerificationResult:
        """ШАГ 1: Проверка клиента в кошельке."""
        await self._simulate_rpc_call()
        account = self._find_account(client_id_or_address)

        if not account:
            logger.warning(f"[{self.provider_name}] Шаг 1: Клиент '{client_id_or_address}' не найден в кошельке.")
            return ClientVerificationResult(
                is_valid=False,
                exists=False,
                is_active=False,
                reason="Клиент или адрес кошелька не зарегистрирован в системе кошелька."
            )

        if account.is_blocked or not account.is_active:
            logger.warning(f"[{self.provider_name}] Шаг 1: Кошелек '{client_id_or_address}' заблокирован или неактивен.")
            return ClientVerificationResult(
                is_valid=False,
                exists=True,
                is_active=False,
                reason="Кошелек клиента заблокирован службой комплаенса или деактивирован."
            )

        logger.info(f"[{self.provider_name}] Шаг 1: Клиент '{client_id_or_address}' успешно верифицирован в кошельке.")
        return ClientVerificationResult(
            is_valid=True,
            exists=True,
            is_active=True,
            details={
                "address": account.address,
                "wallet_type": account.wallet_type,
                "kyc_verified": True
            }
        )

    async def get_wallet_data(self, client_id_or_address: str, currency: str) -> WalletDataResult:
        """ШАГ 2: Запрос на данные кошелька (сеть, комиссия, nonce)."""
        await self._simulate_rpc_call()
        account = self._find_account(client_id_or_address)
        if not account:
            raise ValueError(f"Account {client_id_or_address} not found during data fetch.")

        # Оценка комиссии сети (Gas fee / miner fee)
        fee = Decimal("0.50") if currency.upper() in ["USDT", "USDC"] else Decimal("0.00005")

        logger.info(f"[{self.provider_name}] Шаг 2: Получены метаданные кошелька {account.address}: сеть={account.network}, fee={fee} {currency}")
        return WalletDataResult(
            network=account.network,
            address=account.address,
            wallet_type=account.wallet_type,
            estimated_fee=fee,
            nonce=account.nonce,
            contract_address="0xc2132D05D31c914a87C6611C10748AEb04B58e8F" if currency.upper() == "USDT" else None,
            extra_info={"supports_eip1559": True, "sync_status": "synced"}
        )

    async def check_balance(
        self,
        client_id_or_address: str,
        currency: str,
        required_amount: Decimal
    ) -> BalanceCheckResult:
        """ШАГ 3: Повторный запрос на чек баланса клиента."""
        await self._simulate_rpc_call()
        account = self._find_account(client_id_or_address)
        if not account:
            return BalanceCheckResult(
                sufficient=False,
                available_balance=Decimal("0.00"),
                required_amount=required_amount,
                currency=currency,
                details={"error": "Account not found"}
            )

        cur = currency.upper()
        available = account.balances.get(cur, Decimal("0.00"))
        is_sufficient = available >= required_amount

        logger.info(
            f"[{self.provider_name}] Шаг 3: Повторный чек баланса: Требуется={required_amount} {cur}, "
            f"Доступно={available} {cur}, Достаточно={is_sufficient}"
        )

        return BalanceCheckResult(
            sufficient=is_sufficient,
            available_balance=available,
            required_amount=required_amount,
            currency=cur,
            details={
                "pending_unconfirmed_incoming": Decimal("0.00"),
                "confirmed_balance": available
            }
        )

    async def execute_transfer(
        self,
        client_id_or_address: str,
        currency: str,
        amount: Decimal,
        order_id: str
    ) -> TransferExecutionResult:
        """ШАГ 4: Списание / проведение транзакции."""
        await self._simulate_rpc_call()
        account = self._find_account(client_id_or_address)
        cur = currency.upper()

        if not account or account.balances.get(cur, Decimal("0.00")) < amount:
            return TransferExecutionResult(
                success=False,
                error="Недостаточно баланса на момент списания"
            )

        # Списываем баланс в имитаторе
        account.balances[cur] -= amount
        account.nonce += 1

        # Формируем псевдо-хеш транзакции блокчейна
        raw_hash_data = f"{account.address}:{amount}:{cur}:{order_id}:{account.nonce}:{uuid.uuid4()}"
        tx_hash = "0x" + hashlib.sha256(raw_hash_data.encode()).hexdigest()

        logger.info(f"[{self.provider_name}] Шаг 4: Платеж успешно списан. TxHash: {tx_hash}")
        return TransferExecutionResult(
            success=True,
            tx_hash=tx_hash
        )

    async def health_check(self) -> bool:
        return True

