from app.config import settings
from app.providers.base import BaseWalletProvider
from app.providers.mock_provider import MockWalletProvider
from app.providers.web3_provider import Web3EVMWalletProvider
from app.providers.btc_provider import BitcoinRPCWalletProvider
from app.core.logger import logger


class WalletProviderFactory:
    """
    Фабрика для создания и получения адаптера криптокошелька.
    Позволяет подключать любые новые провайдеры без изменения бизнес-логики сервиса.
    """

    _instance: BaseWalletProvider = None

    @classmethod
    def get_provider(cls, provider_type: str = None) -> BaseWalletProvider:
        if cls._instance is not None and provider_type is None:
            return cls._instance

        ptype = (provider_type or settings.WALLET_PROVIDER_TYPE).lower()

        if ptype == "mock":
            logger.info("Инициализация провайдера: MockWalletProvider")
            instance = MockWalletProvider(latency_ms=settings.MOCK_NETWORK_LATENCY_MS)
        elif ptype in ["web3", "web3_evm", "evm"]:
            logger.info(f"Инициализация провайдера: Web3EVMWalletProvider -> {settings.WEB3_RPC_URL}")
            instance = Web3EVMWalletProvider(rpc_url=settings.WEB3_RPC_URL)
        elif ptype in ["bitcoin", "bitcoin_rpc", "btc"]:
            logger.info(f"Инициализация провайдера: BitcoinRPCWalletProvider -> {settings.BITCOIN_RPC_URL}")
            instance = BitcoinRPCWalletProvider(
                rpc_url=settings.BITCOIN_RPC_URL,
                rpc_user=settings.BITCOIN_RPC_USER,
                rpc_password=settings.BITCOIN_RPC_PASSWORD
            )
        else:
            logger.warning(f"Неизвестный провайдер '{ptype}'. По умолчанию используется MockWalletProvider.")
            instance = MockWalletProvider(latency_ms=settings.MOCK_NETWORK_LATENCY_MS)

        if provider_type is None:
            cls._instance = instance
        return instance

    @classmethod
    def set_provider(cls, provider: BaseWalletProvider):
        """Возможность подменить провайдер (например, в юнит-тестах)."""
        cls._instance = provider

