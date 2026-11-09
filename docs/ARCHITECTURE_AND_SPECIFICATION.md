# Архитектура и спецификация сервиса оплаты

---

## 1. Требования

### Требования к исполнению 5-этапного пайплайна

1. **Этап 1: Прием и валидация запроса от внешнего сервера.**
   * Прием входящего запроса по HTTP (POST JSON).
   * Обязательные параметры:
     * `service_id` — уникальный идентификатор вызывающего сервиса;
     * `order_id` — уникальный номер заказа во внешней системе;
     * `client_id` — идентификатор клиента или публичный крипто-адрес;
     * `amount` — сумма платежа (строго больше нуля);
     * `currency` — тикер криптовалюты/токена (`USDT`, `BTC`, `ETH`).
   * Контроль идемпотентности: при повторном запросе с совпадающей связкой `(service_id, order_id)` сервис не должен выполнять повторные списания, а обязан сразу вернуть ранее сохраненный результат.

2. **Этап 2: Проверка клиента в кошельке.**
   * От кошелька требуется подтверждение: аккаунт/адрес зарегистрирован, активен и не заблокирован (комплаенс/санкции).
   * При сбое проверки процесс немедленно останавливается со статусом `REJECTED`, последующие этапы не выполняются.

3. **Этап 3: Запрос данных кошелька и сети.**
   * От кошелька требуется предоставить: идентификатор сети, тип кошелька/адреса, оценку сетевой комиссии (gas fee / miner fee) и текущий nonce.

4. **Этап 4: Повторный чек баланса.**
   * Баланс клиента запрашивается **повторно** непосредственно перед транзакцией (для исключения race condition и двойной траты).
   * Условие выполнения: `доступный баланс >= сумма платежа + расчетная комиссия`. При нехватке средств — отказ со статусом `REJECTED`.

5. **Этап 5: Проведение транзакции и возврат ответа.**
   * Требуется списать баланс / отправить подписанную транзакцию в сеть и получить уникальный идентификатор (`transaction_hash`).
   * В итоговом ответе вызывающему сервису возвращается статус (`APPROVED` или `REJECTED`), hash и протокол каждого из пройденных этапов с таймстемпами.

### Требования для интеграции криптокошельков
* Изоляция бизнес-логики: процессинг платежей не должен зависеть от специфики конкретного блокчейна.
* Унифицированный интерфейс: подключение любого Open Source кошелька (EVM/Geth, Bitcoin Core, Electrum, BTCPay Server, Mock) реализуется через единый абстрактный контракт (`BaseWalletProvider`).
* Расширяемость: добавление нового кошелька должно производиться без изменения кода ядра сервиса.
* Асинхронность: все сетевые вызовы к узлам и нодам кошельков должны быть неблокирующими (AsyncIO).

---

## 2. Диаграммы системы

### Диаграмма 1: Контекстная диаграмма (Context Diagram)
Определяет границы платежного шлюза, внешние вызывающие сервисы и подключаемые блокчейн-ноды:

```mermaid
graph LR
    subgraph Clients ["Вызывающие сервисы и пользователи"]
        ExternalService["<b>Внешний сервис</b><br/>(Интернет-магазин / Биллинг)"]
        AdminUser["<b>Администратор / Разработчик</b>"]
        WebhookReceiver["<b>Webhook Приемник</b><br/>(Callback endpoint)"]
    end

    subgraph CoreGateway ["Платежный шлюз (Наша система)"]
        GatewaySystem["<b>Crypto Payment Gateway</b><br/>• 1. Прием запроса и проверка идемпотентности<br/>• 2. Проверка клиента в кошельке<br/>• 3. Запрос данных кошелька и fee<br/>• 4. Повторный чек баланса<br/>• 5. Проведение оплаты и возврат ответа<br/>• Логирование шагов и сохранение"]
    end

    subgraph CryptoWallets ["Open Source криптокошельки и ноды"]
        EVMNode["<b>EVM Node (Web3 RPC)</b><br/>(Geth, Nethermind, Anvil, Polygon)"]
        BTCNode["<b>Bitcoin Core / Electrum RPC</b><br/>(bitcoind, BTCPay Server)"]
        MockNode["<b>Mock Wallet</b><br/>(Встроенный симулятор)"]
        Database[("<b>SQLite DB</b><br/>(payments.db)")]
    end

    ExternalService -->|"1. Запрос на оплату (POST)"| GatewaySystem
    GatewaySystem -->|"5. Ответ: статус, tx_hash, шаги"| ExternalService

    AdminUser -->|"Мониторинг (/dashboard, /docs)"| GatewaySystem

    GatewaySystem -->|"2-4. Проверки и списание (JSON-RPC)"| EVMNode
    GatewaySystem -->|"2-4. Проверки и списание (RPC)"| BTCNode
    GatewaySystem -->|"2-4. Проверки и списание (Mock)"| MockNode

    GatewaySystem -->|"Запись транзакций и аудита"| Database
    GatewaySystem -.->|"Асинхронный Webhook (HMAC SHA-256)"| WebhookReceiver
```

---

### Диаграмма 2: Диаграмма последовательности (Sequence Diagram)
Показывает хронологию 5 этапов и поведение при ошибках на этапах проверки клиента и баланса:

```mermaid
sequenceDiagram
    autonumber
    actor External as Внешний сервис
    participant GW as Payment Gateway
    participant Wallet as Криптокошелек (Provider)
    participant DB as База данных (SQLite)

    rect rgb(245, 245, 255)
        Note over External,GW: ЭТАП 1: Прием и валидация запроса
        External->>GW: POST /api/v1/payments/process
        GW->>DB: Проверка на дубликат (service_id + order_id)
        opt Заказ уже существует
            GW-->>External: Возврат ранее сохраненного результата
        end
    end

    rect rgb(240, 248, 255)
        Note over GW,Wallet: ЭТАП 2: Проверка клиента в кошельке
        GW->>Wallet: verify_client(client_id, currency)
        Wallet-->>GW: Result (существует, активен)
    end
    alt Клиент не найден / заблокирован
        GW->>DB: Сохранить статус REJECTED
        GW-->>External: Ответ: REJECTED (Этап 2 не пройден)
    end

    rect rgb(245, 255, 250)
        Note over GW,Wallet: ЭТАП 3: Запрос данных кошелька и сети
        GW->>Wallet: get_wallet_data(client_id, currency)
        Wallet-->>GW: Result (сеть, тип адреса, комиссия fee, nonce)
    end

    rect rgb(255, 250, 240)
        Note over GW,Wallet: ЭТАП 4: Повторный чек баланса
        GW->>Wallet: check_balance(client_id, currency, amount)
        Wallet-->>GW: Result (баланс, достаточно ли)
    end
    alt Баланса недостаточно
        GW->>DB: Сохранить статус REJECTED
        GW-->>External: Ответ: REJECTED (Недостаточно средств)
    end

    rect rgb(240, 255, 240)
        Note over GW,Wallet: ЭТАП 5: Проведение транзакции и возврат ответа
        GW->>Wallet: execute_transfer(client_id, amount, order_id)
        Wallet-->>GW: Result (tx_hash)
    end

    GW->>DB: Сохранить статус APPROVED и tx_hash
    GW-->>External: Ответ: APPROVED + tx_hash + аудит всех шагов
```

---

### Диаграмма 3: Диаграмма состояний (State Machine Diagram)
Отображает переходы статусов платежа по этапам:

```mermaid
stateDiagram-v2
    [*] --> PENDING: ЭТАП 1: Получен и валидирован запрос
    PENDING --> VERIFYING: ЭТАП 2: Проверка клиента
    
    VERIFYING --> REJECTED: Клиент не найден или заблокирован
    VERIFYING --> FETCHING_DATA: Клиент подтвержден -> ЭТАП 3: Запрос данных
    
    FETCHING_DATA --> FAILED: Ошибка ноды кошелька
    FETCHING_DATA --> CHECKING_BALANCE: Данные получены -> ЭТАП 4: Чек баланса
    
    CHECKING_BALANCE --> REJECTED: Баланс < Сумма + Комиссия
    CHECKING_BALANCE --> EXECUTING: Баланс подтвержден -> ЭТАП 5: Списание
    
    EXECUTING --> FAILED: Ошибка отправки транзакции
    EXECUTING --> APPROVED: Транзакция подтверждена (tx_hash получен)

    APPROVED --> [*]
    REJECTED --> [*]
    FAILED --> [*]
```

---

### Диаграмма 4: Диаграмма классов (Class Diagram)
Показывает структуру классов и полиморфизм адаптеров кошельков:

```mermaid
classDiagram
    class BaseWalletProvider {
        <<interface>>
        +verify_client(client_id, currency) ClientVerificationResult
        +get_wallet_data(client_id, currency) WalletDataResult
        +check_balance(client_id, currency, amount) BalanceCheckResult
        +execute_transfer(client_id, currency, amount, order_id) TransferExecutionResult
        +health_check() bool
    }

    class MockWalletProvider {
        +verify_client(...)
        +get_wallet_data(...)
        +check_balance(...)
        +execute_transfer(...)
    }

    class Web3EVMWalletProvider {
        -rpc_url: str
        +verify_client(...)
        +get_wallet_data(...)
        +check_balance(...)
        +execute_transfer(...)
    }

    class BitcoinRPCWalletProvider {
        -rpc_url: str
        +verify_client(...)
        +get_wallet_data(...)
        +check_balance(...)
        +execute_transfer(...)
    }

    class PaymentProcessingService {
        -provider: BaseWalletProvider
        -repository: PaymentRepository
        +process_payment(request) PaymentResponse
    }

    class SQLitePaymentRepository {
        -db_path: str
        +save(payment)
        +get_by_id(id)
        +get_by_order_id(service_id, order_id)
    }

    BaseWalletProvider <|.. MockWalletProvider : реализует
    BaseWalletProvider <|.. Web3EVMWalletProvider : реализует
    BaseWalletProvider <|.. BitcoinRPCWalletProvider : реализует

    PaymentProcessingService --> BaseWalletProvider : использует абстракцию
    PaymentProcessingService --> SQLitePaymentRepository : сохраняет в базу
```

---

## 3. Подход к архитектуре

В проекте используется **Гексагональная архитектура (Ports and Adapters)**:

1. **Доменное ядро (`PaymentProcessingService`):**
   * Содержит только бизнес-логику последовательного выполнения этапов и правила смены статусов.
   * Ядро ничего не знает о протоколах HTTP, структуре таблиц SQL и деталях блокчейнов.
2. **Порты (Интерфейсы):**
   * `BaseWalletProvider` — порт взаимодействия с кошельками.
   * `PaymentRepository` — порт сохранения данных.
3. **Адаптеры:**
   * Входные адаптеры: контроллеры FastAPI (`payments.py`, `wallets.py`), переводящие входящие HTTP-запросы в вызовы ядра.
   * Выходные адаптеры:
     * `MockWalletProvider` — симулятор кошелька для тестов;
     * `Web3EVMWalletProvider` — адаптер для EVM-нод (Geth/Nethermind) по JSON-RPC;
     * `BitcoinRPCWalletProvider` — адаптер для Bitcoin Core / Electrum;
     * `SQLitePaymentRepository` — адаптер персистентного хранения в файле SQLite.

**Преимущество:** подключение любого нового Open Source кошелька (TON, Solana, Monero) сводится к написанию одного адаптера без изменения существующей бизнес-логики.

---

## 4. Где и как применен SOLID

### S — Single Responsibility (Единственная ответственность)
Каждый модуль решает строго одну задачу:
* `PaymentProcessingService` ([`app/services/payment_service.py`](app/services/payment_service.py)) — отвечает только за пошаговую координацию этапов платежа.
* `BaseWalletProvider` и адаптеры ([`app/providers/`](app/providers/)) — отвечают только за сетевое общение с кошельками и блокчейн-узлами.
* `SQLitePaymentRepository` ([`app/services/storage.py`](app/services/storage.py)) — отвечает только за операции сохранения и чтения из базы SQLite.
* `WebhookNotificationService` ([`app/services/webhook_service.py`](app/services/webhook_service.py)) — отвечает только за расчет HMAC-подписи и отправку вебхуков.
* `schemas.py` ([`app/models/schemas.py`](app/models/schemas.py)) — отвечает только за валидацию структур данных.

### O — Open/Closed (Открытость к расширению, закрытость к изменению)
* Чтобы добавить поддержку нового Open Source криптокошелька, **не нужно менять ни одной строчки** в `PaymentProcessingService` или в API-контроллерах.
* Достаточно создать новый класс адаптера (например, `TonWalletProvider`), унаследованный от `BaseWalletProvider`, и зарегистрировать его в фабрике `WalletProviderFactory`. Ядро готово к работе с новым кошельком без изменений.

### L — Liskov Substitution (Подстановка Лисков)
* Любой адаптер кошелька (`MockWalletProvider`, `Web3EVMWalletProvider`, `BitcoinRPCWalletProvider`) может быть передан в `PaymentProcessingService` вместо базового интерфейса.
* Все они соблюдают один и тот же контракт входных и выходных типов (`ClientVerificationResult`, `WalletDataResult`, `BalanceCheckResult`, `TransferExecutionResult`), не ломая логику оркестратора.

### I — Interface Segregation (Разделение интерфейсов)
* Интерфейс `BaseWalletProvider` содержит минимально необходимый набор из 4 методов (`verify_client`, `get_wallet_data`, `check_balance`, `execute_transfer`), строго соответствующий операциям с кошельком. В нем нет лишних методов (стейкинг, экспорт приватных ключей, минтинг).
* Эндпоинты API разделены на отдельные независимые модули: `/payments`, `/wallets`, `/health`, `/dashboard`.

### D — Dependency Inversion (Инверсия зависимостей)
* Высокоуровневый модуль `PaymentProcessingService` не создает и не импортирует конкретные классы `MockWalletProvider` или `Web3EVMWalletProvider`.
* Он зависит только от абстракции `BaseWalletProvider`, которая передается ему извне через конструктор (Dependency Injection):
  ```python
  class PaymentProcessingService:
      def __init__(self, provider: BaseWalletProvider, repository: PaymentRepository = None):
          self.provider = provider
          self.repository = repository
  ```
* В FastAPI связывание выполняется через механизм внедрения зависимостей `Depends(get_wallet_provider)` в [`app/api/deps.py`](app/api/deps.py), что позволяет легко подменять провайдеры в тестах.
