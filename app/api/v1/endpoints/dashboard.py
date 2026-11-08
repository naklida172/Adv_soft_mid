from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Дашборд (Visual Dashboard)"])

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Payment Gateway Dashboard & Monitoring</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans">
  <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
    <div class="flex items-center space-x-3">
      <div class="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30">
        ⚡
      </div>
      <div>
        <h1 class="text-lg font-bold tracking-tight">Crypto Payment Gateway</h1>
        <p class="text-xs text-slate-400">Шлюз обработки платежей &bull; Пайплайн из 4 шагов проверки</p>
      </div>
    </div>
    <div class="flex items-center space-x-3 text-xs">
      <a href="/docs" target="_blank" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition">Swagger API</a>
      <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></span> Service Online
      </span>
    </div>
  </header>

  <main class="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Левая колонка: Форма симуляции внешнего запроса -->
    <section class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
      <h2 class="text-sm font-semibold uppercase tracking-wider text-indigo-400 mb-4 flex items-center">
        <span>Эмуляция запроса от сервиса</span>
      </h2>
      <form id="payForm" class="space-y-4">
        <div>
          <label class="block text-xs font-medium text-slate-300 mb-1">Вызывающий сервис</label>
          <input type="text" id="service_id" value="ecommerce_market_v1" class="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" required>
        </div>

        <div>
          <label class="block text-xs font-medium text-slate-300 mb-1">ID Заказа (Order ID)</label>
          <input type="text" id="order_id" class="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" required>
        </div>

        <div>
          <label class="block text-xs font-medium text-slate-300 mb-1">Сценарий / Клиент в кошельке</label>
          <select id="clientPreset" class="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
            <option value="client_rich_01|150.00|USDT">✓ Успех: client_rich_01 (баланс 50,000 USDT)</option>
            <option value="client_poor_02|500.00|USDT">✗ Отказ шаг 3: client_poor_02 (баланс всего 15 USDT)</option>
            <option value="client_blocked_03|50.00|USDT">✗ Отказ шаг 1: client_blocked_03 (заблокирован)</option>
            <option value="ghost_user_999|100.00|USDT">✗ Отказ шаг 1: ghost_user_999 (клиент не найден)</option>
            <option value="btc_client_04|0.05|BTC">✓ Успех BTC: btc_client_04 (SegWit)</option>
          </select>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-medium text-slate-300 mb-1">Сумма</label>
            <input type="number" step="0.0001" id="amount" value="150.00" class="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" required>
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-300 mb-1">Валюта</label>
            <input type="text" id="currency" value="USDT" class="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" required>
          </div>
        </div>

        <button type="submit" id="submitBtn" class="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-2.5 rounded-lg text-sm transition shadow-lg shadow-indigo-600/30 flex items-center justify-center space-x-2">
          <span>Отправить в Payment Gateway</span>
        </button>
      </form>
    </section>

    <!-- Правая колонка: Протокол выполнения цепочки шагов и список транзакций -->
    <section class="lg:col-span-2 space-y-6">
      <!-- Детали последнего платежа и 4 этапа -->
      <div id="lastResultBox" class="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <div class="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-300">Пайплайн последнего платежа</h2>
          <span id="badgeStatus" class="px-2.5 py-1 text-xs rounded-full bg-slate-800 text-slate-400">Ожидание запроса</span>
        </div>

        <!-- 4 Шага -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs mb-4" id="stepsCards">
          <div id="stepCard-1" class="p-3 rounded-lg border border-slate-800 bg-slate-950/60">
            <div class="font-bold text-slate-400 mb-1">1. Проверка клиента</div>
            <div class="text-[11px] text-slate-500" id="stepText-1">Ожидание...</div>
          </div>
          <div id="stepCard-2" class="p-3 rounded-lg border border-slate-800 bg-slate-950/60">
            <div class="font-bold text-slate-400 mb-1">2. Данные кошелька</div>
            <div class="text-[11px] text-slate-500" id="stepText-2">Ожидание...</div>
          </div>
          <div id="stepCard-3" class="p-3 rounded-lg border border-slate-800 bg-slate-950/60">
            <div class="font-bold text-slate-400 mb-1">3. Повторный чек баланса</div>
            <div class="text-[11px] text-slate-500" id="stepText-3">Ожидание...</div>
          </div>
          <div id="stepCard-4" class="p-3 rounded-lg border border-slate-800 bg-slate-950/60">
            <div class="font-bold text-slate-400 mb-1">4. Проведение оплаты</div>
            <div class="text-[11px] text-slate-500" id="stepText-4">Ожидание...</div>
          </div>
        </div>

        <div id="lastResultDetails" class="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs font-mono text-slate-400 overflow-x-auto max-h-36">
          Отправьте форму слева, чтобы увидеть процесс обработки в реальном времени.
        </div>
      </div>

      <!-- Таблица истории транзакций -->
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-300">История платежей (SQLite Audit)</h2>
          <button onclick="loadPayments()" class="text-xs text-indigo-400 hover:text-indigo-300">Обновить ⟳</button>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-950 text-slate-400 border-b border-slate-800">
              <tr>
                <th class="py-2.5 px-3">ID Платежа</th>
                <th class="py-2.5 px-3">Заказ</th>
                <th class="py-2.5 px-3">Клиент</th>
                <th class="py-2.5 px-3">Сумма</th>
                <th class="py-2.5 px-3">Статус</th>
              </tr>
            </thead>
            <tbody id="paymentsTableBody" class="divide-y divide-slate-800">
              <tr>
                <td colspan="5" class="py-4 text-center text-slate-500">Загрузка данных...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </main>

  <script>
    function generateOrderId() {
      return 'ORD-' + Math.floor(100000 + Math.random() * 900000);
    }
    document.getElementById('order_id').value = generateOrderId();

    document.getElementById('clientPreset').addEventListener('change', (e) => {
      const [clientId, amount, cur] = e.target.value.split('|');
      document.getElementById('amount').value = amount;
      document.getElementById('currency').value = cur;
    });

    async function loadPayments() {
      try {
        const res = await fetch('/api/v1/payments?limit=15');
        const list = await res.json();
        const tbody = document.getElementById('paymentsTableBody');
        tbody.innerHTML = '';
        if (list.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-slate-500">Пока нет транзакций</td></tr>';
          return;
        }
        list.forEach(p => {
          const isSuccess = p.status === 'APPROVED';
          const badgeClass = isSuccess ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-rose-950 text-rose-400 border-rose-800';
          const tr = document.createElement('tr');
          tr.className = 'hover:bg-slate-800/50 cursor-pointer transition';
          tr.onclick = () => renderResult(p);
          tr.innerHTML = `
            <td class="py-2.5 px-3 font-mono">${p.payment_id}</td>
            <td class="py-2.5 px-3">${p.order_id}</td>
            <td class="py-2.5 px-3 text-slate-400">${p.client_id}</td>
            <td class="py-2.5 px-3 font-semibold">${p.amount} ${p.currency}</td>
            <td class="py-2.5 px-3">
              <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border ${badgeClass}">
                ${p.status}
              </span>
            </td>
          `;
          tbody.appendChild(tr);
        });
      } catch (err) {
        console.error(err);
      }
    }

    function renderResult(data) {
      const isSuccess = data.status === 'APPROVED';
      const badge = document.getElementById('badgeStatus');
      badge.textContent = data.status;
      badge.className = `px-2.5 py-1 text-xs rounded-full font-bold border ${isSuccess ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-rose-950 text-rose-400 border-rose-800'}`;

      // Сброс шагов
      for (let i = 1; i <= 4; i++) {
        const card = document.getElementById(`stepCard-${i}`);
        const txt = document.getElementById(`stepText-${i}`);
        card.className = "p-3 rounded-lg border border-slate-800 bg-slate-950/60";
        txt.textContent = "Пропущен";
      }

      // Заполнение пройденных шагов
      (data.steps || []).forEach((s, idx) => {
        const stepNum = idx + 1;
        if (stepNum > 4) return;
        const card = document.getElementById(`stepCard-${stepNum}`);
        const txt = document.getElementById(`stepText-${stepNum}`);
        if (s.status === 'SUCCESS') {
          card.className = "p-3 rounded-lg border border-emerald-800/80 bg-emerald-950/30";
          txt.textContent = "✓ " + s.message;
        } else {
          card.className = "p-3 rounded-lg border border-rose-800/80 bg-rose-950/30";
          txt.textContent = "✗ " + s.message;
        }
      });

      document.getElementById('lastResultDetails').textContent = JSON.stringify(data, null, 2);
    }

    document.getElementById('payForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('submitBtn');
      btn.disabled = true;
      btn.innerHTML = '<span>Обработка 4 шагов...</span>';

      const [selectedClientId] = document.getElementById('clientPreset').value.split('|');

      const payload = {
        service_id: document.getElementById('service_id').value,
        order_id: document.getElementById('order_id').value,
        client_id: selectedClientId,
        amount: parseFloat(document.getElementById('amount').value),
        currency: document.getElementById('currency').value,
        description: "Платеж через web dashboard"
      };

      try {
        const res = await fetch('/api/v1/payments/process', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        renderResult(data);
        await loadPayments();
        document.getElementById('order_id').value = generateOrderId();
      } catch (err) {
        alert("Ошибка вызова шлюза: " + err);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>Отправить в Payment Gateway</span>';
      }
    });

    loadPayments();
  </script>
</body>
</html>
"""

@router.get("/dashboard", response_class=HTMLResponse, summary="Интерактивный Dashboard и мониторинг транзакций")
async def get_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

