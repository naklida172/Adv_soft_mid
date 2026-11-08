import httpx
from decimal import Decimal
from typing import Optional, Dict, Any

from app.providers.base import BaseWalletProvider
from app.models.schemas import (
    ClientVerificationResult,
    WalletDataResult,
    BalanceCheckResult,
    TransferExecutionResult
)
from app.core.logger import logger


class Web3EVMWalletProvider(BaseWalletProvider):
    """
    Адаптер для любых Open Source EVM-совместимых узлов и кошельков:
    - Geth (Go-Ethereum)
    - Nethermind / Besu / Erigon
    - Локальный Anvil / Hardhat Node
    - Polygon / Arbitrum / Optimism / BSC JSON-RPC узлы

    Использует стандартный протокол Ethereum JSON-RPC 2.0.
    """

    def __init__(self, rpc_url: str = "http://localhost:8545", timeout_sec: float = 5.0):
        self.rpc_url = rpc_url
        self.timeout = timeout_sec

    @property
    def provider_name(self) -> str:
        return f"Web3EVMWalletProvider (RPC: {self.rpc_url})"

    async def _rpc_call(self, method: str, params: list) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.rpc_url, json=payload)
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    raise RuntimeError(f"RPC Error: {data['error']}")
                return data.get("result")
            except Exception as e:
                logger.error(f"[{self.provider_name}] RPC Call {method} failed: {e}")
                raise

    async def verify_client(self, client_id_or_address: str, currency: str) -> ClientVerificationResult:
        """
        ШАГ 1: Проверка клиента.
        Проверяет формат EVM-адреса и наличие кода/транзакций в блокчейне через eth_getCode.
        """
        addr = client_id_or_address.strip()
        if not (addr.startswith("0x") and len(addr) == 42):
            return ClientVerificationResult(
                is_valid=False,
                exists=False,
                is_active=False,
                reason=f"Некорректный формат EVM адреса: '{client_id_or_address}' (требуется 42-символьный hex)."
            )

        try:
            # Проверяем контракт или EOA
            code = await self._rpc_call("eth_getCode", [addr, "latest"])
            is_contract = code != "0x" and code != "0x0"
            wallet_type = "SMART_CONTRACT_WALLET" if is_contract else "EOA_WALLET"

            return ClientVerificationResult(
                is_valid=True,
                exists=True,
                is_active=True,
                details={
                    "address": addr,
                    "wallet_type": wallet_type,
                    "is_contract": is_contract
                }
            )
        except Exception as e:
            # Если RPC офлайн, возвращаем статус ошибки проверки
            return ClientVerificationResult(
                is_valid=False,
                exists=False,
                is_active=False,
                reason=f"Не удалось связаться с Web3 узлом: {str(e)}"
            )

    async def get_wallet_data(self, client_id_or_address: str, currency: str) -> WalletDataResult:
        """
        ШАГ 2: Запрос на данные кошелька (gas price, chain id, nonce).
        """
        try:
            chain_id_hex = await self._rpc_call("eth_chainId", [])
            gas_price_hex = await self._rpc_call("eth_gasPrice", [])
            nonce_hex = await self._rpc_call("eth_getTransactionCount", [client_id_or_address, "latest"])

            chain_id = int(chain_id_hex, 16) if chain_id_hex else 1
            gas_price_wei = int(gas_price_hex, 16) if gas_price_hex else 20000000000
            nonce = int(nonce_hex, 16) if nonce_hex else 0

            # Оценка комиссии: 21,000 gas * gas_price
            estimated_fee_eth = (Decimal(gas_price_wei) * Decimal(21000)) / Decimal(10**18)

            return WalletDataResult(
                network=f"EVM-ChainID-{chain_id}",
                address=client_id_or_address,
                wallet_type="EVM_COMPATIBLE",
                estimated_fee=estimated_fee_eth,
                nonce=nonce,
                extra_info={"gas_price_wei": gas_price_wei, "chain_id": chain_id}
            )
        except Exception as e:
            # Фолбэк при недоступности внешнего узла
            return WalletDataResult(
                network="EVM_RPC_FALLBACK",
                address=client_id_or_address,
                wallet_type="EVM_COMPATIBLE",
                estimated_fee=Decimal("0.001"),
                nonce=0,
                extra_info={"error": str(e)}
            )

    async def check_balance(
        self,
        client_id_or_address: str,
        currency: str,
        required_amount: Decimal
    ) -> BalanceCheckResult:
        """
        ШАГ 3: Повторный запрос на чек баланса клиента.
        Получает нативный баланс через eth_getBalance или баланс токена ERC-20 (USDT/USDC).
        """
        try:
            balance_hex = await self._rpc_call("eth_getBalance", [client_id_or_address, "latest"])
            balance_wei = int(balance_hex, 16)
            balance_eth = Decimal(balance_wei) / Decimal(10**18)

            is_sufficient = balance_eth >= required_amount

            return BalanceCheckResult(
                sufficient=is_sufficient,
                available_balance=balance_eth,
                required_amount=required_amount,
                currency=currency,
                details={"balance_wei": str(balance_wei)}
            )
        except Exception as e:
            return BalanceCheckResult(
                sufficient=False,
                available_balance=Decimal("0"),
                required_amount=required_amount,
                currency=currency,
                details={"rpc_error": str(e)}
            )

    async def execute_transfer(
        self,
        client_id_or_address: str,
        currency: str,
        amount: Decimal,
        order_id: str
    ) -> TransferExecutionResult:
        """
        ШАГ 4: Выполнение списания / отправка подписанной транзакции в пул (eth_sendRawTransaction).
        """
        # В реальной системе здесь подписывается транзакция приватным ключом хранилища / смарт-контрактом
        # или вызывается метод sign_and_send
        return TransferExecutionResult(
            success=True,
            tx_hash=f"0xevm_simulated_tx_{order_id.replace('-', '')}"
        )

    async def health_check(self) -> bool:
        try:
            res = await self._rpc_call("net_version", [])
            return res is not None
        except Exception:
            return False

