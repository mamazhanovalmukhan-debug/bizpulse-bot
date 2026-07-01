-- Users
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    full_name TEXT,
    username TEXT,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Businesses
CREATE TABLE IF NOT EXISTS businesses (
    id SERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT DEFAULT 'other',
    timezone TEXT DEFAULT 'Europe/Moscow',
    is_blocked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Locations
CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    address TEXT,
    open_time INT DEFAULT 9,
    close_time INT DEFAULT 21,
    timezone TEXT DEFAULT 'Europe/Moscow',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Business users (role mapping)
CREATE TABLE IF NOT EXISTS business_users (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE SET NULL,
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    role TEXT DEFAULT 'employee',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(business_id, user_id)
);

-- Employee invites
CREATE TABLE IF NOT EXISTS employee_invites (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE SET NULL,
    role TEXT DEFAULT 'employee',
    token TEXT UNIQUE NOT NULL,
    used_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ,
    is_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Shifts
CREATE TABLE IF NOT EXISTS shifts (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    opened_by BIGINT REFERENCES users(telegram_id),
    closed_by BIGINT REFERENCES users(telegram_id),
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    opening_cash NUMERIC(12,2) DEFAULT 0,
    closing_cash NUMERIC(12,2),
    status TEXT DEFAULT 'open',
    opening_comment TEXT,
    closing_comment TEXT,
    date DATE DEFAULT CURRENT_DATE
);

-- Cash movements
CREATE TABLE IF NOT EXISTS cash_movements (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    shift_id INT REFERENCES shifts(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    comment TEXT,
    source TEXT DEFAULT 'manual',
    created_by BIGINT REFERENCES users(telegram_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cash checks
CREATE TABLE IF NOT EXISTS cash_checks (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    shift_id INT REFERENCES shifts(id) ON DELETE CASCADE,
    expected_cash NUMERIC(12,2),
    actual_cash NUMERIC(12,2),
    difference NUMERIC(12,2),
    status TEXT DEFAULT 'ok',
    created_by BIGINT REFERENCES users(telegram_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Shift notes
CREATE TABLE IF NOT EXISTS shift_notes (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    shift_id INT REFERENCES shifts(id) ON DELETE CASCADE,
    created_by BIGINT REFERENCES users(telegram_id),
    note TEXT NOT NULL,
    visible_next_shift BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Subscriptions
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE UNIQUE,
    plan TEXT DEFAULT 'mvp',
    status TEXT DEFAULT 'trial',
    trial_started_at TIMESTAMPTZ DEFAULT NOW(),
    trial_ends_at TIMESTAMPTZ,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Payments
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(telegram_id),
    provider TEXT DEFAULT 'telegram_payments',
    amount INT NOT NULL,
    currency TEXT DEFAULT 'RUB',
    status TEXT DEFAULT 'pending',
    external_payment_id TEXT UNIQUE,
    payment_url TEXT,
    paid_at TIMESTAMPTZ,
    receipt_url TEXT,
    tax_status TEXT,
    raw_payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Competitors
CREATE TABLE IF NOT EXISTS competitors (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    website_url TEXT,
    telegram_url TEXT,
    vk_url TEXT,
    instagram_url TEXT,
    yandex_maps_url TEXT,
    two_gis_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Competitor updates
CREATE TABLE IF NOT EXISTS competitor_updates (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    competitor_id INT REFERENCES competitors(id) ON DELETE CASCADE,
    source TEXT,
    title TEXT,
    text TEXT,
    url TEXT,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    ai_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- AI reports
CREATE TABLE IF NOT EXISTS ai_reports (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    type TEXT,
    content TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- POS integrations
CREATE TABLE IF NOT EXISTS pos_integrations (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    api_key_encrypted TEXT,
    login_encrypted TEXT,
    password_encrypted TEXT,
    organization_id TEXT,
    terminal_group_id TEXT,
    status TEXT DEFAULT 'inactive',
    last_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- POS transactions
CREATE TABLE IF NOT EXISTS pos_transactions (
    id SERIAL PRIMARY KEY,
    business_id INT REFERENCES businesses(id) ON DELETE CASCADE,
    location_id INT REFERENCES locations(id) ON DELETE CASCADE,
    provider TEXT,
    external_id TEXT UNIQUE,
    amount NUMERIC(12,2),
    payment_type TEXT,
    product_name TEXT,
    quantity NUMERIC(10,3),
    category TEXT,
    occurred_at TIMESTAMPTZ,
    raw_payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_shifts_location_date ON shifts(location_id, date);
CREATE INDEX IF NOT EXISTS idx_cash_movements_shift ON cash_movements(shift_id);
CREATE INDEX IF NOT EXISTS idx_cash_movements_business ON cash_movements(business_id, created_at);
CREATE INDEX IF NOT EXISTS idx_business_users_user ON business_users(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_business ON payments(business_id);
