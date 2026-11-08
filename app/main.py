import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.v1.router import api_v1_router
from app.core.logger import logger
from app.core.exceptions import GatewayException


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        description=(
            "### Платежный микросервис-шлюз (Payment Gateway Service)\n\n"
            "Сервис предназначен для обработки запросов на оплату от любых внешних сервисов "
            "(интернет-магазинов, биллинговых платформ, ботов и партнерских систем).\n\n"
            "#### Реализованный бизнес-пайплайн:\n"
            "1. **Входной запрос от сервиса** (`POST /api/v1/payments/process`)\n"
            "2. **Проверка клиента в кошельке** (валидность адреса, активность, отсутствие блокировок)\n"
            "3. **Запрос данных кошелька** (сеть, тип кошелька, оценка gas/network fee, nonce)\n"
            "4. **Повторный чек баланса** (проверка доступности необходимой суммы средств с учетом комиссии перед списанием)\n"
            "5. **Исполнение платежа и возврат ответа** (фиксация транзакции, генерация tx hash, полный аудит шагов)\n\n"
            "#### Архитектура расширяемости кошельков:\n"
            "Построен по принципу Hexagonal Architecture (Ports and Adapters). В будущем позволяет легко подключать "
            "любой **Open Source криптокошелек** или ноду (Bitcoin Core, Electrum, Web3/EVM Geth, BTCPay Server, TON и др.) "
            "через реализацию единого интерфейса `BaseWalletProvider`."
        ),
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware логирования запросов
    @app.middleware("http")
    async def log_requests_middleware(request: Request, call_next):
        start_time = time.time()
        client_host = request.client.host if request.client else "unknown"
        logger.info(f"Входящий запрос: {request.method} {request.url.path} от {client_host}")
        
        response = await call_next(request)
        process_time_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(f"Завершен запрос: {request.method} {request.url.path} -> {response.status_code} ({process_time_ms} ms)")
        return response

    # Глобальный обработчик доменных ошибок
    @app.exception_handler(GatewayException)
    async def gateway_exception_handler(request: Request, exc: GatewayException):
        logger.warning(f"Ошибка шлюза: code={exc.code}, msg={exc.message}")
        return JSONResponse(
            status_code=400,
            content={"error_code": exc.code, "message": exc.message}
        )

    # Подключение роутеров:
    # 1. Основной версионированный префикс (/api/v1/payments/process, /api/v1/health)
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
    # 2. Корневой алиас для совместимости (/payments/process, /health, /dashboard)
    app.include_router(api_v1_router)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.PROJECT_VERSION,
            "docs": "/docs",
            "dashboard": "/dashboard",
            "health": f"{settings.API_V1_PREFIX}/health"
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

