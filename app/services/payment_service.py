import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from app.models.schemas import (
    PaymentInitiateRequest,
    PaymentResponse,
    PaymentStatus,
    StepName,
    StepStatus,
    PipelineStepLog
)
from app.providers.base import BaseWalletProvider
from app.services.storage import PaymentRepository, payment_repo
from app.core.logger import logger


class PaymentProcessingService:
    """
    Основной сервис оркестрации платежей.
    Реализует обязательную 4-этапную цепочку:
    1. Проверка клиента в кошельке
    2. Запрос метаданных кошелька
    3. Повторный запрос на чек баланса
    4. Проведение транзакции и возврат ответа внешнему сервису
    """

    def __init__(self, provider: BaseWalletProvider, repository: PaymentRepository = None):
        self.provider = provider
        self.repository = repository or payment_repo

    async def process_payment(self, req: PaymentInitiateRequest) -> PaymentResponse:
        # Проверка идемпотентности
        existing_payment = await self.repository.get_by_order_id(req.service_id, req.order_id)
        if existing_payment:
            logger.info(f"Найден повторный запрос заказа {req.order_id} от сервиса {req.service_id}. Возврат кэшированного результата.")
            return existing_payment

        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc)
        steps: List[PipelineStepLog] = []

        logger.info(f"=== Начало обработки платежа {payment_id} для заказа '{req.order_id}' от сервиса '{req.service_id}' ===")
        logger.info(f"Параметры: клиент='{req.client_id}', сумма={req.amount} {req.currency}")

        # -------------------------------------------------------------
        # ЭТАП 1: Проверка клиента в кошельке
        # -------------------------------------------------------------
        logger.info(f"[{payment_id}] ШАГ 1: Запрос проверки клиента '{req.client_id}' в криптокошельке...")
        try:
            client_verif = await self.provider.verify_client(req.client_id, req.currency)
        except Exception as e:
            logger.error(f"[{payment_id}] Исключение при проверке клиента: {e}")
            step_log = PipelineStepLog(
                step=StepName.VERIFY_CLIENT,
                status=StepStatus.FAILED,
                message=f"Ошибка связи с провайдером кошелька: {str(e)}"
            )
            steps.append(step_log)
            return await self._finalize_payment(
                payment_id, req, PaymentStatus.FAILED, False, steps, created_at,
                failure_reason=f"Сбой провайдера кошелька: {str(e)}"
            )

        if not client_verif.is_valid:
            logger.warning(f"[{payment_id}] ШАГ 1 НЕ ПРОЙДЕН: {client_verif.reason}")
            steps.append(PipelineStepLog(
                step=StepName.VERIFY_CLIENT,
                status=StepStatus.FAILED,
                message=client_verif.reason or "Клиент не прошел верификацию в кошельке.",
                data=client_verif.details
            ))
            return await self._finalize_payment(
                payment_id, req, PaymentStatus.REJECTED, False, steps, created_at,
                failure_reason=client_verif.reason or "Клиент отклонен кошельком"
            )

        steps.append(PipelineStepLog(
            step=StepName.VERIFY_CLIENT,
            status=StepStatus.SUCCESS,
            message="Клиент найден и активен в кошельке.",
            data=client_verif.details
        ))
        logger.info(f"[{payment_id}] ШАГ 1 УСПЕШНО ЗАВЕРШЕН.")

        # -------------------------------------------------------------
        # ЭТАП 2: Запрос на данные кошелька (сеть, тип, комиссия)
        # -------------------------------------------------------------
        logger.info(f"[{payment_id}] ШАГ 2: Запрос данных кошелька и расчет параметров сети...")
        try:
            wallet_data = await self.provider.get_wallet_data(req.client_id, req.currency)
            steps.append(PipelineStepLog(
                step=StepName.GET_WALLET_DATA,
                status=StepStatus.SUCCESS,
                message=f"Данные получены: сеть {wallet_data.network}, тип {wallet_data.wallet_type}",
                data={
                    "network": wallet_data.network,
                    "address": wallet_data.address,
                    "wallet_type": wallet_data.wallet_type,
                    "estimated_fee": str(wallet_data.estimated_fee),
                    "nonce": wallet_data.nonce
                }
            ))
            logger.info(f"[{payment_id}] ШАГ 2 УСПЕШНО: Сеть={wallet_data.network}, расчет комиссии={wallet_data.estimated_fee}")
        except Exception as e:
            logger.error(f"[{payment_id}] Ошибка на шаге 2 получения данных кошелька: {e}")
            steps.append(PipelineStepLog(
                step=StepName.GET_WALLET_DATA,
                status=StepStatus.FAILED,
                message=f"Не удалось получить данные кошелька: {str(e)}"
            ))
            return await self._finalize_payment(
                payment_id, req, PaymentStatus.FAILED, False, steps, created_at,
                failure_reason=f"Сбой получения метаданных кошелька: {str(e)}"
            )

        # -------------------------------------------------------------
        # ЭТАП 3: Повторный запрос на чек баланса
        # -------------------------------------------------------------
        # Проверяем сумму платежа (с учетом комиссии, если токен)
        total_required = req.amount
        logger.info(f"[{payment_id}] ШАГ 3: Повторный запрос на чек баланса клиента для суммы {total_required} {req.currency}...")
        try:
            balance_result = await self.provider.check_balance(req.client_id, req.currency, total_required)
        except Exception as e:
            logger.error(f"[{payment_id}] Ошибка на шаге 3 повторного чека баланса: {e}")
            steps.append(PipelineStepLog(
                step=StepName.CHECK_BALANCE,
                status=StepStatus.FAILED,
                message=f"Не удалось проверить баланс: {str(e)}"
            ))
            return await self._finalize_payment(
                payment_id, req, PaymentStatus.FAILED, False, steps, created_at,
                failure_reason=f"Сбой проверки баланса: {str(e)}"
            )

        if not balance_result.sufficient:
            msg = (
                f"Недостаточно средств. Требуется: {total_required} {req.currency}, "
                f"доступно: {balance_result.available_balance} {req.currency}."
            )
            logger.warning(f"[{payment_id}] ШАГ 3 НЕ ПРОЙДЕН: {msg}")
            steps.append(PipelineStepLog(
                step=StepName.CHECK_BALANCE,
                status=StepStatus.FAILED,
                message=msg,
                data={
                    "available_balance": str(balance_result.available_balance),
                    "required_amount": str(total_required),
                    "currency": req.currency
                }
            ))
            return await self._finalize_payment(
                payment_id, req, PaymentStatus.REJECTED, False, steps, created_at,
                fee_estimated=wallet_data.estimated_fee,
                failure_reason=msg
            )

        steps.append(PipelineStepLog(
            step=StepName.CHECK_BALANCE,
            status=StepStatus.SUCCESS,
            message=f"Баланс подтвержден: доступно {balance_result.available_balance} {req.currency}",
            data={
                "available_balance": str(balance_result.available_balance),
                "required_amount": str(total_required)
            }
        ))
        logger.info(f"[{payment_id}] ШАГ 3 УСПЕШНО: Баланс подтвержден.")

        # -------------------------------------------------------------
        # ЭТАП 4: Списание / Исполнение транзакции
        # -------------------------------------------------------------
        logger.info(f"[{payment_id}] ШАГ 4: Выполнение списания {req.amount} {req.currency}...")
        try:
            transfer = await self.provider.execute_transfer(
                client_id_or_address=req.client_id,
                currency=req.currency,
                amount=req.amount,
                order_id=req.order_id
            )
        except Exception as e:
            logger.error(f"[{payment_id}] Ошибка при списании: {e}")
            steps.append(PipelineStepLog(
                step=StepName.EXECUTE_PAYMENT,
                status=StepStatus.FAILED,
                message=f"Ошибка транзакции: {str(e)}"
            ))
            return await self._finalize_payment(
                payment_id, req, PaymentStatus.FAILED, False, steps, created_at,
                fee_estimated=wallet_data.estimated_fee,
                failure_reason=f"Ошибка списания: {str(e)}"
            )

        if not transfer.success:
            steps.append(PipelineStepLog(
                step=StepName.EXECUTE_PAYMENT,
                status=StepStatus.FAILED,
                message=transfer.error or "Отказ выполнения транзакции"
            ))
            return await self._finalize_payment(
                payment_id, req, PaymentStatus.FAILED, False, steps, created_at,
                fee_estimated=wallet_data.estimated_fee,
                failure_reason=transfer.error
            )

        steps.append(PipelineStepLog(
            step=StepName.EXECUTE_PAYMENT,
            status=StepStatus.SUCCESS,
            message=f"Транзакция успешно подтверждена. Hash: {transfer.tx_hash}",
            data={"tx_hash": transfer.tx_hash}
        ))
        logger.info(f"[{payment_id}] ШАГ 4 УСПЕШНО: Транзакция проведена! Hash: {transfer.tx_hash}")

        # Возвращаемся с успехом вызывающему сервису
        return await self._finalize_payment(
            payment_id=payment_id,
            req=req,
            status=PaymentStatus.APPROVED,
            is_success=True,
            steps=steps,
            created_at=created_at,
            tx_hash=transfer.tx_hash,
            fee_estimated=wallet_data.estimated_fee
        )

    async def _finalize_payment(
        self,
        payment_id: str,
        req: PaymentInitiateRequest,
        status: PaymentStatus,
        is_success: bool,
        steps: List[PipelineStepLog],
        created_at: datetime,
        tx_hash: str = None,
        fee_estimated: Decimal = None,
        failure_reason: str = None
    ) -> PaymentResponse:
        response = PaymentResponse(
            payment_id=payment_id,
            order_id=req.order_id,
            service_id=req.service_id,
            client_id=req.client_id,
            amount=req.amount,
            currency=req.currency,
            status=status,
            is_success=is_success,
            transaction_hash=tx_hash,
            fee_estimated=fee_estimated,
            failure_reason=failure_reason,
            steps=steps,
            created_at=created_at,
            completed_at=datetime.now(timezone.utc)
        )
        await self.repository.save(response)
        logger.info(f"=== Платеж {payment_id} завершен со статусом [{status.value}] (is_success={is_success}) ===")
        return response
