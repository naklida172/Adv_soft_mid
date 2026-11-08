"""
Скрипт-симулятор внешнего сервиса (E-commerce / Billing service).
Демонстрирует обращение к Payment Gateway Service и показывает пошаговый результат:
1. Успешный платеж (клиент найден -> данные получены -> баланс подтвержден -> списание -> ответ APPROVED)
2. Платеж несуществующего клиента (отказ на шаге 1)
3. Платеж с недостаточным балансом (отказ на шаге 3)
"""
import sys
import json
import httpx
import asyncio

BASE_URL = "http://localhost:8000"


def print_step(title: str):
    print(f"\n{'='*70}\n[СЦЕНАРИЙ] {title}\n{'='*70}")


def print_response_details(res_json: dict):
    if not isinstance(res_json, dict):
        print(f"Неожиданный ответ сервера: {res_json}")
        return

    print(f"ID платежа:     {res_json.get('payment_id')}")
    print(f"Статус:         {res_json.get('status')}")
    print(f"Успех:          {res_json.get('is_success')}")
    print(f"Сумма:          {res_json.get('amount')} {res_json.get('currency')}")
    if res_json.get('transaction_hash'):
        print(f"Tx Hash:        {res_json.get('transaction_hash')}")
    if res_json.get('failure_reason'):
        print(f"Причина отказа: {res_json.get('failure_reason')}")

    print("\nПротокол выполнения цепочки шагов:")
    steps = res_json.get('steps', [])
    if not steps:
        print("  (Нет зафиксированных шагов)")
    for idx, s in enumerate(steps, 1):
        status_icon = "✓" if s.get('status') == "SUCCESS" else "✗"
        print(f"  [{idx}] {status_icon} Шаг: {s.get('step', ''):<16} | Статус: {s.get('status', ''):<8} | {s.get('message', '')}")


async def main():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # 0. Health check
        try:
            health = await client.get("/api/v1/health")
            print(f"Статус сервера: {health.json()}")
        except Exception as e:
            print(f"Ошибка соединения с сервером {BASE_URL}: {e}")
            print("Убедитесь, что сервис запущен: python -m uvicorn app.main:app --port 8000")
            return

        # Сценарий 1: Успешная оплата
        print_step("1. Успешный платеж (проверка клиента -> метаданные -> баланс -> одобрено)")
        res1 = await client.post("/api/v1/payments/process", json={
            "service_id": "external_market_service",
            "order_id": f"order_macbook_{int(asyncio.get_event_loop().time() * 1000)}",
            "client_id": "client_rich_01",
            "amount": "2199.00",
            "currency": "USDT",
            "description": "Оплата заказа MacBook Pro M3"
        })
        print_response_details(res1.json())

        # Сценарий 2: Клиент не найден в кошельке (отклонение на шаге 1)
        print_step("2. Попытка оплаты от неизвестного клиента (отказ на шаге 1)")
        res2 = await client.post("/api/v1/payments/process", json={
            "service_id": "external_market_service",
            "order_id": f"order_ghost_{int(asyncio.get_event_loop().time() * 1000)}",
            "client_id": "usr_unknown_ghost_88",
            "amount": "100.00",
            "currency": "USDT"
        })
        print_response_details(res2.json())

        # Сценарий 3: Недостаточно средств при повторном чеке баланса (отказ на шаге 3)
        print_step("3. Клиент с низким балансом (отказ на шаге 3 повторного чека баланса)")
        res3 = await client.post("/api/v1/payments/process", json={
            "service_id": "external_market_service",
            "order_id": f"order_car_{int(asyncio.get_event_loop().time() * 1000)}",
            "client_id": "client_poor_02",
            "amount": "5000.00",
            "currency": "USDT"
        })
        print_response_details(res3.json())


if __name__ == "__main__":
    asyncio.run(main())
