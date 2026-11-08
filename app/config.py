import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Crypto Payment Gateway Service"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    
    # Сервер
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # Безопасность взаимодействия между сервисами
    # Если список пуст или "*", проверка API ключа опциональна для dev режима
    SERVICE_API_KEYS: List[str] = ["external-service-secret-key-1", "test-api-key"]
    REQUIRE_API_KEY: bool = False  # Включить True для обязательной проверки X-API-Key

    # Тип крипто-провайдера: "mock", "web3_evm", "bitcoin_rpc"
    WALLET_PROVIDER_TYPE: str = "mock"
    
    # Настройки для Web3 / EVM провайдера (Open source node: Geth, Anvil, Polygon, etc.)
    WEB3_RPC_URL: str = "http://localhost:8545"
    
    # Настройки для Bitcoin / Electrum RPC
    BITCOIN_RPC_URL: str = "http://localhost:8332"
    BITCOIN_RPC_USER: str = "rpcuser"
    BITCOIN_RPC_PASSWORD: str = "rpcpassword"
    
    # Имитация задержек сети криптокошелька (в миллисекундах)
    MOCK_NETWORK_LATENCY_MS: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()

