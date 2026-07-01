-- ============================================================
-- BizPulse v6 production migrations — исправлены HIGH-1, HIGH-2
-- ============================================================

-- 1. Anomalies
CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE SET NULL,
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    severity TEXT DEFAULT 'info',   -- info / warning / critical
    title TEXT NOT NULL,
    description TEXT,
    recommendation TEXT,
    status TEXT DEFAULT 'open',     -- open / resolved
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_anomalies_business ON anomalies(business_id, status);
CREATE INDEX IF NOT EXISTS idx_anomalies_type_date ON anomalies(business_id, type, status);

-- 2. Audit logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INT,
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_business ON audit_logs(business_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);

--    cash_sales + card_sales + aggregator_sales
ALTER TABLE shift_reports ADD COLUMN IF NOT EXISTS deposits NUMERIC(12,2) DEFAULT 0;

-- 4. Поля в businesses
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;

-- 5. HIGH-1 FIX: три критичных индекса
-- subscriptions.business_id — вызывается при каждом запросе через SubscriptionMiddleware
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_biz
    ON subscriptions(business_id);

-- shifts.business_id + date — get_today_shifts, get_week_shifts
CREATE INDEX IF NOT EXISTS idx_shifts_business
    ON shifts(business_id, date);

-- payments.external_payment_id — get_payment_by_internal_id (идемпотентность оплаты)
CREATE INDEX IF NOT EXISTS idx_payments_ext_id
    ON payments(external_payment_id)
    WHERE external_payment_id IS NOT NULL;

-- 6. Дополнительные индексы для производительности
CREATE INDEX IF NOT EXISTS idx_shift_reports_type
    ON shift_reports(shift_id, report_type);

CREATE INDEX IF NOT EXISTS idx_cash_checks_business
    ON cash_checks(business_id, created_at);
