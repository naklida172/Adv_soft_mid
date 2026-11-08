import sqlite3
import json
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.models.schemas import PaymentResponse, PaymentStatus, PipelineStepLog
from app.core.logger import logger


class SQLitePaymentRepository:
    """
    Персистентный репозиторий на базе SQLite для сохранения платежей и аудита шагов.
    """

    def __init__(self, db_path: str = "payments.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    is_success INTEGER NOT NULL,
                    transaction_hash TEXT,
                    fee_estimated TEXT,
                    failure_reason TEXT,
                    steps_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(service_id, order_id)
                )
            """)
            conn.commit()

    def _row_to_payment(self, row: sqlite3.Row) -> PaymentResponse:
        steps_data = json.loads(row["steps_json"])
        steps = [PipelineStepLog(**s) for s in steps_data]

        return PaymentResponse(
            payment_id=row["payment_id"],
            order_id=row["order_id"],
            service_id=row["service_id"],
            client_id=row["client_id"],
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            status=PaymentStatus(row["status"]),
            is_success=bool(row["is_success"]),
            transaction_hash=row["transaction_hash"],
            fee_estimated=Decimal(row["fee_estimated"]) if row["fee_estimated"] else None,
            failure_reason=row["failure_reason"],
            steps=steps,
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
        )

    async def save(self, payment: PaymentResponse) -> PaymentResponse:
        steps_json = json.dumps([s.model_dump(mode="json") for s in payment.steps])
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO payments (
                    payment_id, order_id, service_id, client_id, amount,
                    currency, status, is_success, transaction_hash, fee_estimated,
                    failure_reason, steps_json, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                payment.payment_id,
                payment.order_id,
                payment.service_id,
                payment.client_id,
                str(payment.amount),
                payment.currency,
                payment.status.value,
                1 if payment.is_success else 0,
                payment.transaction_hash,
                str(payment.fee_estimated) if payment.fee_estimated is not None else None,
                payment.failure_reason,
                steps_json,
                payment.created_at.isoformat(),
                payment.completed_at.isoformat() if payment.completed_at else None
            ))
            conn.commit()
        return payment

    async def get_by_id(self, payment_id: str) -> Optional[PaymentResponse]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_payment(row)
        return None

    async def get_by_order_id(self, service_id: str, order_id: str) -> Optional[PaymentResponse]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM payments WHERE service_id = ? AND order_id = ?",
                (service_id, order_id)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_payment(row)
        return None

    async def list_all(self, limit: int = 50) -> List[PaymentResponse]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM payments ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [self._row_to_payment(r) for r in rows]

    async def clear_all(self):
        """Для тестов."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM payments")
            conn.commit()


# Синглтон репозитория с постоянным сохранением в SQLite
PaymentRepository = SQLitePaymentRepository
payment_repo = SQLitePaymentRepository(db_path="payments.db")
