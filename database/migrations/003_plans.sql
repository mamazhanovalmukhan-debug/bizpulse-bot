-- ============================================================
-- BizPulse v3 — тарифные планы
-- ============================================================

-- 1. Таблица тарифов
CREATE TABLE IF NOT EXISTS subscription_plans (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,         -- START / GROW / NETWORK / ENTERPRISE
    name TEXT NOT NULL,
    max_locations INT,                  -- NULL = безлимит
    price_amount INT NOT NULL DEFAULT 0, -- в копейках
    price_currency TEXT DEFAULT 'RUB',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Начальное заполнение тарифов (идемпотентно)
INSERT INTO subscription_plans (code, name, max_locations, price_amount, price_currency)
VALUES
    ('START',      'Старт',      1,    199000, 'RUB'),
    ('GROW',       'Рост',       5,    349000, 'RUB'),
    ('NETWORK',    'Сеть',       15,   599000, 'RUB'),
    ('ENTERPRISE', 'Enterprise', NULL, 0,      'RUB')
ON CONFLICT (code) DO UPDATE
    SET name=EXCLUDED.name,
        max_locations=EXCLUDED.max_locations,
        price_amount=EXCLUDED.price_amount;

-- 3. Новые поля в subscriptions
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_code TEXT DEFAULT 'START';
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_id INT REFERENCES subscription_plans(id) ON DELETE SET NULL;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS subscription_started_at TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS subscription_ends_at TIMESTAMPTZ;

-- Подтягиваем plan_id для существующих строк
UPDATE subscriptions SET plan_id = (
    SELECT id FROM subscription_plans WHERE code='START'
) WHERE plan_id IS NULL;

-- 4. Поле plan_code в payments
ALTER TABLE payments ADD COLUMN IF NOT EXISTS plan_code TEXT DEFAULT 'START';

-- 5. Индексы
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan ON subscriptions(plan_code);
CREATE INDEX IF NOT EXISTS idx_payments_plan ON payments(plan_code);
