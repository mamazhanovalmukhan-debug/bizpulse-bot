# BizPulse v6 — Цифровой управляющий для малого бизнеса

Telegram-бот для контроля кофеен, шаурма, пекарен, табачных магазинов и розницы.

---

## Что умеет

- **Смены и касса** — открытие/закрытие смены, наличные/безнал/агрегаторы, расходы, возвраты, инкассация. Бот считает ожидаемый остаток и алертит при расхождении.
- **Сотрудники** — invite-ссылки, роли, аналитика эффективности.
- **Склад** — товары, категории, поставщики, приёмка, инвентаризация, алерты о низком остатке.
- **Business Advisor** — утренние рекомендации на основе данных: что заказать, кто проседает, где падает выручка.
- **Health Score** — оценка состояния бизнеса 0–100 каждый день.
- **ИИ-аналитика** — ежедневный и еженедельный разбор через Groq/Llama.
- **Тарифы** — START/GROW/NETWORK/ENTERPRISE, смена тарифа, Telegram Payments.
- **Поддержка** — тикет-система с уведомлением admin.
- **Audit Log** — журнал всех действий.
- **Аномалии** — автодетектирование падений, расхождений, проблемных сотрудников.

---

## Тарифы

| Тариф      | Точки | Цена       |
|------------|-------|------------|
| Старт      | 1     | 1 990 ₽/мес |
| Рост       | до 5  | 3 490 ₽/мес |
| Сеть       | до 15 | 5 990 ₽/мес |
| Enterprise | 16+   | индивид.   |

30 дней бесплатно — один раз на Telegram-аккаунт.

---

## Архитектура

```
app/
├── main.py                      # Точка входа
├── config.py                    # Все настройки (env + бизнес-правила)
├── database/
│   ├── session.py               # asyncpg pool
│   ├── models.py                # 100+ SQL-функций
│   └── migrations/
│       ├── 001_init.sql         # Базовая схема
│       ├── 002_v3.sql           # Расширения v3
│       ├── 003_plans.sql        # Тарифные планы
│       └── 004_production.sql   # Аномалии, audit_log
├── handlers/
│   ├── cancel.py                # Универсальная отмена FSM
│   ├── start.py                 # /start, invite-ссылки
│   ├── onboarding.py            # Регистрация бизнеса
│   ├── billing.py               # Тариф и оплата
│   ├── owner.py                 # Команды владельца
│   ├── employee.py              # Полный цикл смены
│   ├── payments.py              # Telegram Payments
│   ├── admin.py                 # Системная админка
│   ├── support.py               # Тикеты поддержки
│   ├── legal.py                 # Документы
│   └── demo.py                  # Демо-данные (admin + DEBUG only)
├── services/
│   ├── cash_service.py          # Кассовая логика и формулы
│   ├── shift_service.py         # Бизнес-логика смен
│   ├── ai_service.py            # ИИ через Groq
│   ├── advisor_service.py       # Business Advisor + Health Score
│   ├── analytics_service.py     # Аналитика сотрудников
│   ├── anomaly_service.py       # Детектор аномалий
│   ├── audit_service.py         # Audit log
│   ├── plan_service.py          # Тарифная система
│   ├── payment_service.py       # Оплата
│   ├── invite_service.py        # Invite-ссылки
│   ├── notification_service.py  # Уведомления
│   ├── subscription_service.py  # Подписка
│   └── pos/                     # POS-заглушки (iiko, МойСклад, Контур)
├── middlewares/
│   ├── error_handler.py         # Единый обработчик ошибок
│   ├── auth.py                  # Rate limit + upsert user
│   ├── role.py                  # Определение роли
│   └── subscription.py          # Блокировка при expired
├── keyboards/
│   ├── owner.py
│   ├── employee.py
│   └── admin.py
├── scheduler/
│   ├── jobs.py                  # Все задачи планировщика
│   └── setup.py                 # APScheduler
└── utils/
    ├── validators.py            # Централизованная валидация
    ├── formatting.py            # fmt_money, parse_money
    ├── encryption.py            # Fernet
    └── dates.py                 # Timezone helpers
```

---

## Запуск локально

```bash
git clone <repo>
cd bizpulse

# Зависимости
pip install -r requirements.txt

# Настройка
cp .env.example .env
# Заполни .env

# БД — создай PostgreSQL базу
createdb bizpulse

# Запуск (миграции применяются автоматически)
python -m app.main
```

---

## Деплой на Railway

**1. Создай проект в Railway**

```
railway.app → New Project → Deploy from GitHub
```

**2. Добавь PostgreSQL**

```
New → Database → PostgreSQL
```

DATABASE_URL добавится автоматически.

**3. Переменные окружения** (Settings → Variables):

```
BOT_TOKEN=                    # @BotFather → создать бота
BOT_USERNAME=                 # username бота без @
DATABASE_URL=                 # авто из Railway PostgreSQL
ADMIN_IDS=123456789           # твой Telegram ID
SUPPORT_USERNAME=@username    # контакт поддержки
GROQ_API_KEY=                 # console.groq.com
PAYMENT_PROVIDER_TOKEN=       # @BotFather → Payments
PAYMENT_CURRENCY=RUB
DEFAULT_TRIAL_DAYS=30
CASH_TOLERANCE_AMOUNT=100
DEBUG=false
```

**4. Procfile**

```
worker: python -m app.main
```

Миграции применяются автоматически при каждом старте.

---

## Как получить PAYMENT_PROVIDER_TOKEN

1. Напиши @BotFather
2. /mybots → выбери бота
3. Payments → Connect Payment Provider
4. Выбери провайдера (Stripe для теста, ЮKassa для России)
5. Скопируй токен → PAYMENT_PROVIDER_TOKEN

---

## Как работает Trial

- 30 дней бесплатно при регистрации первого бизнеса
- Привязан к Telegram-аккаунту (не к бизнесу)
- Повторный trial невозможен — даже при создании нового бизнеса
- После истечения: только /pay, /support, /subscription доступны
- Сотрудники тоже блокируются

---

## Как работает оплата

1. Владелец нажимает /pay или «Продлить текущий тариф»
2. Бот создаёт invoice с суммой тарифа
3. pre_checkout проверяет: сумму, валюту, тариф, owner
4. После оплаты: подписка продлевается +30 дней
5. При повторной оплате активной подписки: +30 дней к текущей дате окончания
6. Идемпотентность: повторный webhook не продлевает дважды

---

## Как работает Лимит точек

При попытке добавить точку сверх лимита тарифа:

```
На тарифе «Старт» доступно до 1 точки.
Для добавления новой точки перейдите на тариф «Рост» (до 5 точек — 3 490 ₽/мес).
Сменить тариф: /change_plan
```

---

## Кассовая формула

```
cash_expected = cash_start
              + cash_sales
              - expenses
              - refunds
              - collection
              + deposits
```

Правила:
- Касса не может быть отрицательной
- Расход/инкассация/возврат не могут превышать доступные наличные
- Эквайринг и агрегаторы не влияют на физические наличные
- При расхождении > CASH_TOLERANCE_AMOUNT → alert владельцу

---

## Роли

| Роль     | Доступ |
|----------|--------|
| Owner    | Всё: аналитика, сотрудники, тарифы, склад |
| Manager  | Своя точка: смены, отчёты |
| Employee | Открытие/закрытие смены, расходы, поставки |
| Admin    | Системная панель BizPulse |

---

## Команды администратора

```
/admin              — статистика платформы
/admin_plans        — бизнесы и тарифы
/admin_set_plan <id> <код>  — сменить тариф
/admin_extend <id> [дней]   — продлить подписку
/admin_activate <id>        — активировать
/admin_block <id>           — заблокировать
/admin_unblock <id>         — разблокировать
/admin_tickets      — заявки поддержки
/admin_close <id>   — закрыть тикет
/admin_payments     — платежи за 30 дней
/admin_users        — список бизнесов
/broadcast          — рассылка всем владельцам
```

---

## Business Advisor

Каждое утро владелец получает персональные рекомендации:

```
🌅 Советник — Кофейня Утро

Требует внимания:
⚠️ Вчера выручка была на 32% ниже средней — проверьте вечернюю смену.

Рекомендации на сегодня:
• Сегодня стоит заказать: Молоко 3.2% (осталось 2 л).
• Иван 5 смен ниже среднего — рекомендуется проверить.
```

---

## Health Score

Ежедневная оценка 0–100:

- 90–100: 🟢 Отличное состояние
- 70–89:  🟡 Хорошее состояние
- 50–69:  🟠 Есть проблемы
- 0–49:   🔴 Требует внимания

Факторы: незакрытые смены, расхождения кассы, низкий склад, критические аномалии, статус подписки.

---

## Тесты

```bash
# Запуск без БД
python tests/test_cash.py
python tests/test_plans.py
python tests/test_validators.py
```

---

## Оставшиеся ограничения

1. **Склад** — FSM для создания поставок и инвентаризации не реализован (таблицы есть, хендлеры нет).
2. **POS-интеграции** — iiko, МойСклад, Контур — заглушки, нужно реализовать API.
3. **MemoryStorage** — FSM-состояния теряются при перезапуске Railway. Для production нужен RedisStorage.
4. **Health Score** — вычисляется на лету без кэша, при большом количестве бизнесов может быть медленным.
