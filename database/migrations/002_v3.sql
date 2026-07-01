-- ============================================================
-- BizPulse v3 migrations — добавляются поверх 001_init.sql
-- Все statements идемпотентны (IF NOT EXISTS)
-- ============================================================

-- 1. Trial usage — один trial на пользователя
CREATE TABLE IF NOT EXISTS trial_usage (
    id SERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL UNIQUE,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);

-- 2. Расширяем subscriptions (добавляем поля если не существуют)
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS canceled_at TIMESTAMPTZ;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;

-- 3. shift_reports — финансовые итоги смены
CREATE TABLE IF NOT EXISTS shift_reports (
    id SERIAL PRIMARY KEY,
    shift_id INT REFERENCES shifts(id) ON DELETE CASCADE,
    report_type TEXT NOT NULL,  -- opening / interim / closing
    cash_start NUMERIC(12,2) DEFAULT 0,
    cash_sales NUMERIC(12,2) DEFAULT 0,
    card_sales NUMERIC(12,2) DEFAULT 0,
    aggregator_sales NUMERIC(12,2) DEFAULT 0,
    expenses NUMERIC(12,2) DEFAULT 0,
    refunds NUMERIC(12,2) DEFAULT 0,
    collection NUMERIC(12,2) DEFAULT 0,
    deposits NUMERIC(12,2) DEFAULT 0,
    cash_expected NUMERIC(12,2),
    cash_actual NUMERIC(12,2),
    discrepancy NUMERIC(12,2),
    discrepancy_comment TEXT,
    created_by BIGINT REFERENCES users(telegram_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Расширяем payments
ALTER TABLE payments ADD COLUMN IF NOT EXISTS provider_payment_charge_id TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS idempotency_key TEXT UNIQUE;

-- 5. Support tickets
CREATE TABLE IF NOT EXISTS support_tickets (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE SET NULL,
    user_id BIGINT REFERENCES users(telegram_id),
    role TEXT,
    type TEXT,   -- technical / payment / employee / report / other
    message TEXT NOT NULL,
    status TEXT DEFAULT 'open',  -- open / in_progress / closed
    admin_note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

-- 6. Products (склад)
CREATE TABLE IF NOT EXISTS product_categories (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    external_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    category_id INT REFERENCES product_categories(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    unit TEXT DEFAULT 'шт',
    min_stock NUMERIC(10,3) DEFAULT 0,
    current_stock NUMERIC(10,3) DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    external_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Suppliers
CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Deliveries
CREATE TABLE IF NOT EXISTS deliveries (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE SET NULL,
    supplier_id INT REFERENCES suppliers(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'expected',  -- expected / in_progress / received / cancelled
    expected_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    created_by BIGINT REFERENCES users(telegram_id),
    received_by BIGINT REFERENCES users(telegram_id),
    comment TEXT,
    invoice_photo_file_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS delivery_items (
    id SERIAL PRIMARY KEY,
    delivery_id INT REFERENCES deliveries(id) ON DELETE CASCADE,
    product_id INT REFERENCES products(id) ON DELETE SET NULL,
    expected_quantity NUMERIC(10,3) DEFAULT 0,
    actual_quantity NUMERIC(10,3),
    discrepancy NUMERIC(10,3),
    comment TEXT
);

-- 9. Inventory
CREATE TABLE IF NOT EXISTS inventory_sessions (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'in_progress',  -- in_progress / completed / cancelled
    started_by BIGINT REFERENCES users(telegram_id),
    completed_by BIGINT REFERENCES users(telegram_id),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    comment TEXT
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id SERIAL PRIMARY KEY,
    inventory_session_id INT REFERENCES inventory_sessions(id) ON DELETE CASCADE,
    product_id INT REFERENCES products(id) ON DELETE SET NULL,
    expected_quantity NUMERIC(10,3) DEFAULT 0,
    actual_quantity NUMERIC(10,3),
    discrepancy NUMERIC(10,3),
    status TEXT DEFAULT 'pending',  -- pending / counted / skipped
    comment TEXT
);

-- 10. Stock movements
CREATE TABLE IF NOT EXISTS stock_movements (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE SET NULL,
    product_id INT REFERENCES products(id) ON DELETE SET NULL,
    type TEXT NOT NULL,   -- receipt / expense / writeoff / correction / inventory
    quantity NUMERIC(10,3) NOT NULL,
    source_type TEXT,     -- delivery / inventory / manual
    source_id INT,
    comment TEXT,
    created_by BIGINT REFERENCES users(telegram_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 11. Stock alerts
CREATE TABLE IF NOT EXISTS stock_alerts (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE SET NULL,
    product_id INT REFERENCES products(id) ON DELETE SET NULL,
    type TEXT NOT NULL,   -- out_of_stock / low_stock / discrepancy
    message TEXT,
    status TEXT DEFAULT 'open',  -- open / resolved
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- 12. Indexes
CREATE INDEX IF NOT EXISTS idx_shift_reports_shift ON shift_reports(shift_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_business ON support_tickets(business_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);
CREATE INDEX IF NOT EXISTS idx_products_business ON products(business_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_business ON deliveries(business_id, status);
CREATE INDEX IF NOT EXISTS idx_stock_movements_product ON stock_movements(product_id, created_at);
CREATE INDEX IF NOT EXISTS idx_stock_alerts_business ON stock_alerts(business_id, status);
CREATE INDEX IF NOT EXISTS idx_trial_usage_user ON trial_usage(telegram_user_id);
