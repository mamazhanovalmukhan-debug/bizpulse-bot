-- ============================================================
-- BizPulse migration 005 — исправление тарифов и подписок
-- ============================================================

-- 1. Обновляем данные в subscription_plans (идемпотентно)
INSERT INTO subscription_plans (code, name, max_locations, price_amount, price_currency, is_active)
VALUES
    ('START',   'Старт',  1,  199000, 'RUB', TRUE),
    ('GROW',    'Рост',   5,  349000, 'RUB', TRUE),
    ('NETWORK', 'Сеть',   15, 599000, 'RUB', TRUE)
ON CONFLICT (code) DO UPDATE
    SET name          = EXCLUDED.name,
        max_locations = EXCLUDED.max_locations,
        price_amount  = EXCLUDED.price_amount,
        is_active     = TRUE;

-- 2. Enterprise деактивируем из UI (оставляем запись, но is_active=FALSE)
UPDATE subscription_plans
SET is_active = FALSE
WHERE code = 'ENTERPRISE';

-- 3. Для существующих subscriptions без plan_code ставим START
UPDATE subscriptions
SET plan_code = 'START',
    plan_id   = (SELECT id FROM subscription_plans WHERE code = 'START' LIMIT 1)
WHERE plan_code IS NULL OR plan_code = '';

-- 4. Для businesses без subscription создаём expired subscription
-- (чтобы код не падал с NULL при get_subscription)
INSERT INTO subscriptions (business_id, status, plan_code)
SELECT b.id, 'expired', 'START'
FROM businesses b
WHERE NOT EXISTS (
    SELECT 1 FROM subscriptions s WHERE s.business_id = b.id
)
ON CONFLICT (business_id) DO NOTHING;

-- 5. Индекс для быстрого поиска businesses без subscription (для self-repair)
CREATE INDEX IF NOT EXISTS idx_businesses_owner ON businesses(owner_id);
