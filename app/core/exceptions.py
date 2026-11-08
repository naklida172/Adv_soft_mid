class GatewayException(Exception):
    """Базовое исключение платежного шлюза."""
    def __init__(self, message: str, code: str = "GATEWAY_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ClientNotFoundException(GatewayException):
    def __init__(self, client_id: str):
        super().__init__(f"Клиент {client_id} не найден в кошельке.", code="CLIENT_NOT_FOUND")


class ClientSuspendedException(GatewayException):
    def __init__(self, client_id: str, reason: str = "Кошелек заблокирован"):
        super().__init__(f"Кошелек клиента {client_id} недоступен: {reason}.", code="CLIENT_SUSPENDED")


class InsufficientFundsException(GatewayException):
    def __init__(self, required: str, available: str, currency: str):
        super().__init__(
            f"Недостаточно средств. Требуется: {required} {currency}, доступно: {available} {currency}.",
            code="INSUFFICIENT_FUNDS"
        )


class WalletConnectionException(GatewayException):
    def __init__(self, details: str):
        super().__init__(f"Ошибка связи с нодой криптокошелька: {details}", code="WALLET_RPC_ERROR")

