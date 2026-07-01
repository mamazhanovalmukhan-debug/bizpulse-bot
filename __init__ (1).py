"""Все SQL-запросы BizPulse v3."""
import asyncpg
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from database.session import get_pool


# ═══════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════

async def upsert_user(tg_id: int, full_name: str, username: str = "") -> asyncpg.Record:
    return await get_pool().fetchrow(
        """INSERT INTO users (telegram_id, full_name, username)
           VALUES ($1,$2,$3)
           ON CONFLICT (telegram_id) DO UPDATE SET full_name=$2, username=$3
           RETURNING *""",
        tg_id, full_name, username or ""
    )

async def get_user(tg_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow("SELECT * FROM users WHERE telegram_id=$1", tg_id)

async def count_users() -> int:
    return await get_pool().fetchval("SELECT COUNT(*) FROM users")

async def get_all_owner_ids() -> list:
    rows = await get_pool().fetch(
        "SELECT DISTINCT owner_id FROM businesses WHERE is_blocked=FALSE"
    )
    return [r["owner_id"] for r in rows]


# ═══════════════════════════════════════════════════════════════
# TRIAL
# ═══════════════════════════════════════════════════════════════

async def has_used_trial(tg_id: int) -> bool:
    row = await get_pool().fetchrow(
        "SELECT id FROM trial_usage WHERE telegram_user_id=$1", tg_id
    )
    return row is not None

async def create_trial_usage(tg_id: int, business_id: int, days: int = 30):
    from utils.dates import now_utc
    ends = now_utc() + timedelta(days=days)
    await get_pool().execute(
        """INSERT INTO trial_usage (telegram_user_id, business_id, started_at, ended_at)
           VALUES ($1,$2,NOW(),$3)
           ON CONFLICT (telegram_user_id) DO NOTHING""",
        tg_id, business_id, ends
    )


# ═══════════════════════════════════════════════════════════════
# BUSINESSES
# ═══════════════════════════════════════════════════════════════

async def create_business(owner_id: int, name: str, category: str,
                           timezone: str, city: str = "") -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO businesses (owner_id,name,category,timezone,city)
           VALUES ($1,$2,$3,$4,$5) RETURNING id""",
        owner_id, name, category, timezone, city
    )
    return row["id"]

async def get_business_by_owner(owner_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        "SELECT * FROM businesses WHERE owner_id=$1 AND is_blocked=FALSE", owner_id
    )

async def get_business(bid: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow("SELECT * FROM businesses WHERE id=$1", bid)

async def get_all_businesses() -> list:
    return await get_pool().fetch(
        "SELECT * FROM businesses ORDER BY created_at DESC"
    )

async def block_business(bid: int, blocked: bool):
    await get_pool().execute(
        "UPDATE businesses SET is_blocked=$2 WHERE id=$1", bid, blocked
    )

async def touch_business(bid: int):
    await get_pool().execute(
        "UPDATE businesses SET last_active_at=NOW() WHERE id=$1", bid
    )


# ═══════════════════════════════════════════════════════════════
# LOCATIONS
# ═══════════════════════════════════════════════════════════════

async def create_location(business_id: int, name: str, address: str,
                           open_time: int, close_time: int, tz: str) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO locations (business_id,name,address,open_time,close_time,timezone)
           VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
        business_id, name, address, open_time, close_time, tz
    )
    return row["id"]

async def get_locations(business_id: int) -> list:
    return await get_pool().fetch(
        "SELECT * FROM locations WHERE business_id=$1 AND is_active=TRUE ORDER BY id",
        business_id
    )

async def get_location(loc_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow("SELECT * FROM locations WHERE id=$1", loc_id)

async def count_locations(business_id: int) -> int:
    return await get_pool().fetchval(
        "SELECT COUNT(*) FROM locations WHERE business_id=$1 AND is_active=TRUE",
        business_id
    )


# ═══════════════════════════════════════════════════════════════
# BUSINESS USERS
# ═══════════════════════════════════════════════════════════════

async def add_business_user(business_id: int, user_id: int, role: str,
                             location_id: int = None) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO business_users (business_id,location_id,user_id,role)
           VALUES ($1,$2,$3,$4)
           ON CONFLICT (business_id,user_id) DO UPDATE
             SET role=$4, location_id=$2, is_active=TRUE
           RETURNING id""",
        business_id, location_id, user_id, role
    )
    return row["id"]

async def get_business_user(user_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        """SELECT bu.*, b.name as business_name, b.owner_id, b.is_blocked
           FROM business_users bu
           JOIN businesses b ON b.id=bu.business_id
           WHERE bu.user_id=$1 AND bu.is_active=TRUE AND b.is_blocked=FALSE
           LIMIT 1""",
        user_id
    )

async def get_business_users(business_id: int) -> list:
    return await get_pool().fetch(
        """SELECT bu.*, u.full_name, u.username, l.name as location_name
           FROM business_users bu
           JOIN users u ON u.telegram_id=bu.user_id
           LEFT JOIN locations l ON l.id=bu.location_id
           WHERE bu.business_id=$1 AND bu.is_active=TRUE ORDER BY bu.created_at""",
        business_id
    )

async def get_location_employees(location_id: int) -> list:
    return await get_pool().fetch(
        """SELECT bu.*, u.full_name, u.username
           FROM business_users bu
           JOIN users u ON u.telegram_id=bu.user_id
           WHERE bu.location_id=$1 AND bu.is_active=TRUE
             AND bu.role IN ('employee','manager')""",
        location_id
    )

async def count_employees(business_id: int) -> int:
    return await get_pool().fetchval(
        """SELECT COUNT(*) FROM business_users
           WHERE business_id=$1 AND is_active=TRUE AND role='employee'""",
        business_id
    )


# ═══════════════════════════════════════════════════════════════
# INVITES
# ═══════════════════════════════════════════════════════════════

async def create_invite(business_id: int, location_id: int, role: str,
                         token: str, expires_at) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO employee_invites (business_id,location_id,role,token,expires_at)
           VALUES ($1,$2,$3,$4,$5) RETURNING id""",
        business_id, location_id, role, token, expires_at
    )
    return row["id"]

async def get_invite(token: str) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        "SELECT * FROM employee_invites WHERE token=$1", token
    )

async def use_invite(token: str, user_id: int):
    await get_pool().execute(
        "UPDATE employee_invites SET is_used=TRUE,used_by=$2 WHERE token=$1",
        token, user_id
    )


# ═══════════════════════════════════════════════════════════════
# SHIFTS
# ═══════════════════════════════════════════════════════════════

async def open_shift(business_id: int, location_id: int, opened_by: int,
                      opening_cash: float, comment: str = "") -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO shifts (business_id,location_id,opened_by,opening_cash,
           opening_comment,status,date)
           VALUES ($1,$2,$3,$4,$5,'open',CURRENT_DATE) RETURNING id""",
        business_id, location_id, opened_by, opening_cash, comment
    )
    return row["id"]

async def get_open_shift(location_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        "SELECT * FROM shifts WHERE location_id=$1 AND status='open' AND date=CURRENT_DATE",
        location_id
    )

async def close_shift_db(shift_id: int, closed_by: int,
                          closing_cash: float, comment: str = ""):
    await get_pool().execute(
        """UPDATE shifts SET status='closed',closed_at=NOW(),
           closed_by=$2,closing_cash=$3,closing_comment=$4 WHERE id=$1""",
        shift_id, closed_by, closing_cash, comment
    )

async def get_today_shifts(business_id: int) -> list:
    return await get_pool().fetch(
        """SELECT s.*,l.name as location_name
           FROM shifts s JOIN locations l ON l.id=s.location_id
           WHERE s.business_id=$1 AND s.date=CURRENT_DATE ORDER BY s.opened_at""",
        business_id
    )

async def get_week_shifts(business_id: int) -> list:
    return await get_pool().fetch(
        """SELECT s.*,l.name as location_name
           FROM shifts s JOIN locations l ON l.id=s.location_id
           WHERE s.business_id=$1 AND s.date>=CURRENT_DATE-7 ORDER BY s.date DESC""",
        business_id
    )

async def get_last_closed_shift(location_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        """SELECT * FROM shifts WHERE location_id=$1 AND status='closed'
           ORDER BY closed_at DESC LIMIT 1""",
        location_id
    )

async def get_employee_shifts(user_id: int, business_id: int,
                               days: int = 30) -> list:
    return await get_pool().fetch(
        """SELECT s.*,l.name as location_name
           FROM shifts s JOIN locations l ON l.id=s.location_id
           WHERE s.opened_by=$1 AND s.business_id=$2
             AND s.date>=CURRENT_DATE-$3
           ORDER BY s.date DESC""",
        user_id, business_id, days
    )


# ═══════════════════════════════════════════════════════════════
# SHIFT REPORTS
# ═══════════════════════════════════════════════════════════════

async def save_shift_report(shift_id: int, report_type: str,
                             cash_start: float = 0, cash_sales: float = 0,
                             card_sales: float = 0, aggregator_sales: float = 0,
                             expenses: float = 0, refunds: float = 0,
                             collection: float = 0, deposits: float = 0,
                             cash_expected: float = None, cash_actual: float = None,
                             discrepancy: float = None, discrepancy_comment: str = "",
                             created_by: int = None) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO shift_reports
           (shift_id,report_type,cash_start,cash_sales,card_sales,aggregator_sales,
            expenses,refunds,collection,deposits,cash_expected,cash_actual,
            discrepancy,discrepancy_comment,created_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
           RETURNING id""",
        shift_id, report_type, cash_start, cash_sales, card_sales, aggregator_sales,
        expenses, refunds, collection, deposits, cash_expected, cash_actual,
        discrepancy, discrepancy_comment, created_by
    )
    return row["id"]

async def get_shift_reports(shift_id: int) -> list:
    return await get_pool().fetch(
        "SELECT * FROM shift_reports WHERE shift_id=$1 ORDER BY created_at",
        shift_id
    )

async def get_today_reports(business_id: int) -> list:
    return await get_pool().fetch(
        """SELECT sr.*,l.name as location_name
           FROM shift_reports sr
           JOIN shifts s ON s.id=sr.shift_id
           JOIN locations l ON l.id=s.location_id
           WHERE s.business_id=$1 AND sr.created_at::date=CURRENT_DATE
           ORDER BY sr.created_at""",
        business_id
    )

async def get_week_reports(business_id: int) -> list:
    return await get_pool().fetch(
        """SELECT sr.*,l.name as location_name
           FROM shift_reports sr
           JOIN shifts s ON s.id=sr.shift_id
           JOIN locations l ON l.id=s.location_id
           WHERE s.business_id=$1
             AND sr.report_type='closing'
             AND sr.created_at>=NOW()-INTERVAL '7 days'
           ORDER BY sr.created_at""",
        business_id
    )


# ═══════════════════════════════════════════════════════════════
# CASH MOVEMENTS
# ═══════════════════════════════════════════════════════════════

async def add_movement(business_id: int, location_id: int, shift_id: int,
                        mtype: str, amount: float, comment: str = "",
                        created_by: int = None) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO cash_movements
           (business_id,location_id,shift_id,type,amount,comment,created_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
        business_id, location_id, shift_id, mtype, amount, comment, created_by
    )
    return row["id"]

async def get_shift_movements(shift_id: int) -> list:
    return await get_pool().fetch(
        "SELECT * FROM cash_movements WHERE shift_id=$1 ORDER BY created_at",
        shift_id
    )

async def get_business_movements(business_id: int, days: int = 7) -> list:
    return await get_pool().fetch(
        """SELECT * FROM cash_movements
           WHERE business_id=$1 AND created_at>=NOW()-INTERVAL '1 day'*$2
           ORDER BY created_at DESC""",
        business_id, days
    )


# ═══════════════════════════════════════════════════════════════
# CASH CHECKS
# ═══════════════════════════════════════════════════════════════

async def save_cash_check(business_id: int, location_id: int, shift_id: int,
                           expected: float, actual: float, diff: float,
                           status: str, created_by: int) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO cash_checks
           (business_id,location_id,shift_id,expected_cash,actual_cash,
            difference,status,created_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
        business_id, location_id, shift_id, expected, actual, diff, status, created_by
    )
    return row["id"]


# ═══════════════════════════════════════════════════════════════
# SHIFT NOTES
# ═══════════════════════════════════════════════════════════════

async def add_shift_note(business_id: int, location_id: int, shift_id: int,
                          created_by: int, note: str, visible_next: bool = False):
    await get_pool().execute(
        """INSERT INTO shift_notes
           (business_id,location_id,shift_id,created_by,note,visible_next_shift)
           VALUES ($1,$2,$3,$4,$5,$6)""",
        business_id, location_id, shift_id, created_by, note, visible_next
    )

async def get_next_shift_notes(location_id: int) -> list:
    return await get_pool().fetch(
        """SELECT * FROM shift_notes WHERE location_id=$1
           AND visible_next_shift=TRUE
           AND created_at>=NOW()-INTERVAL '7 days'
           ORDER BY created_at DESC LIMIT 5""",
        location_id
    )

async def get_all_stock_notes(business_id: int) -> list:
    rows = await get_pool().fetch(
        """SELECT sn.note FROM shift_notes sn
           WHERE sn.business_id=$1 AND sn.note IS NOT NULL
           ORDER BY sn.created_at DESC LIMIT 50""",
        business_id
    )
    return [r["note"] for r in rows]


# ═══════════════════════════════════════════════════════════════
# SUBSCRIPTIONS
# ═══════════════════════════════════════════════════════════════

async def create_subscription(business_id: int, trial_days: int = 30):
    from utils.dates import now_utc
    ends = now_utc() + timedelta(days=trial_days)
    await get_pool().execute(
        """INSERT INTO subscriptions (business_id,status,trial_started_at,trial_ends_at)
           VALUES ($1,'trial',NOW(),$2)
           ON CONFLICT (business_id) DO NOTHING""",
        business_id, ends
    )

async def get_subscription(business_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        "SELECT * FROM subscriptions WHERE business_id=$1", business_id
    )

async def activate_subscription(business_id: int):
    """Продлить подписку: +30 дней от текущей даты окончания или от сейчас."""
    from utils.dates import now_utc
    now = now_utc()
    sub = await get_subscription(business_id)
    if sub and sub["status"] == "active" and sub["current_period_end"]:
        end = sub["current_period_end"]
        if end.replace(tzinfo=timezone.utc) > now:
            new_end = end.replace(tzinfo=timezone.utc) + timedelta(days=30)
        else:
            new_end = now + timedelta(days=30)
    else:
        new_end = now + timedelta(days=30)
    await get_pool().execute(
        """UPDATE subscriptions SET status='active',
           current_period_start=$2, current_period_end=$3
           WHERE business_id=$1""",
        business_id, now, new_end
    )

async def expire_subscription(business_id: int):
    await get_pool().execute(
        "UPDATE subscriptions SET status='expired' WHERE business_id=$1",
        business_id
    )

async def get_expiring_subs(days: int) -> list:
    from utils.dates import now_utc
    target = now_utc() + timedelta(days=days)
    return await get_pool().fetch(
        """SELECT s.*,b.owner_id,b.name as biz_name FROM subscriptions s
           JOIN businesses b ON b.id=s.business_id
           WHERE s.status='active' AND s.current_period_end::date=$1::date""",
        target
    )

async def get_trial_expiring(days: int) -> list:
    from utils.dates import now_utc
    target = now_utc() + timedelta(days=days)
    return await get_pool().fetch(
        """SELECT s.*,b.owner_id,b.name as biz_name FROM subscriptions s
           JOIN businesses b ON b.id=s.business_id
           WHERE s.status='trial' AND s.trial_ends_at::date=$1::date""",
        target
    )

async def get_sub_stats() -> dict:
    pool = get_pool()
    return {
        "total":   await pool.fetchval("SELECT COUNT(*) FROM subscriptions"),
        "trial":   await pool.fetchval("SELECT COUNT(*) FROM subscriptions WHERE status='trial'"),
        "active":  await pool.fetchval("SELECT COUNT(*) FROM subscriptions WHERE status='active'"),
        "expired": await pool.fetchval("SELECT COUNT(*) FROM subscriptions WHERE status='expired'"),
    }

async def manual_activate_subscription(business_id: int, days: int = 30):
    await activate_subscription(business_id)


# ═══════════════════════════════════════════════════════════════
# PAYMENTS
# ═══════════════════════════════════════════════════════════════

async def create_payment(business_id: int, user_id: int, provider: str,
                          amount: int, internal_id: str,
                          plan_code: str = "START") -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO payments
           (business_id,user_id,provider,amount,external_payment_id,
            idempotency_key,plan_code,status)
           VALUES ($1,$2,$3,$4,$5,$5,$6,'pending') RETURNING id""",
        business_id, user_id, provider, amount, internal_id, plan_code
    )
    return row["id"]

async def get_payment_by_internal_id(internal_id: str) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        "SELECT * FROM payments WHERE external_payment_id=$1", internal_id
    )

async def confirm_payment(internal_id: str, tg_charge_id: str,
                           provider_charge_id: str = "", raw: dict = None):
    await get_pool().execute(
        """UPDATE payments SET status='paid', paid_at=NOW(),
           provider_payment_charge_id=$3, raw_payload=$4
           WHERE external_payment_id=$1 AND status='pending'""",
        internal_id, tg_charge_id,
        provider_charge_id, json.dumps(raw) if raw else None
    )

async def get_month_payments() -> list:
    return await get_pool().fetch(
        """SELECT p.*,b.name as biz_name FROM payments p
           JOIN businesses b ON b.id=p.business_id
           WHERE p.paid_at>=NOW()-INTERVAL '30 days' AND p.status='paid'
           ORDER BY p.paid_at DESC"""
    )

async def get_month_revenue() -> int:
    val = await get_pool().fetchval(
        """SELECT COALESCE(SUM(amount),0) FROM payments
           WHERE paid_at>=NOW()-INTERVAL '30 days' AND status='paid'"""
    )
    return int(val or 0)


# ═══════════════════════════════════════════════════════════════
# SUPPORT TICKETS
# ═══════════════════════════════════════════════════════════════

async def create_ticket(business_id: int, user_id: int, role: str,
                         ticket_type: str, message: str) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO support_tickets
           (business_id,user_id,role,type,message,status)
           VALUES ($1,$2,$3,$4,$5,'open') RETURNING id""",
        business_id, user_id, role, ticket_type, message
    )
    return row["id"]

async def get_open_tickets() -> list:
    return await get_pool().fetch(
        """SELECT t.*,u.full_name,u.username,b.name as biz_name
           FROM support_tickets t
           JOIN users u ON u.telegram_id=t.user_id
           LEFT JOIN businesses b ON b.id=t.business_id
           WHERE t.status!='closed'
           ORDER BY t.created_at DESC LIMIT 50"""
    )

async def get_ticket(ticket_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        """SELECT t.*,u.full_name,b.name as biz_name
           FROM support_tickets t
           JOIN users u ON u.telegram_id=t.user_id
           LEFT JOIN businesses b ON b.id=t.business_id
           WHERE t.id=$1""",
        ticket_id
    )

async def close_ticket(ticket_id: int, admin_note: str = ""):
    await get_pool().execute(
        """UPDATE support_tickets SET status='closed',
           admin_note=$2, closed_at=NOW(), updated_at=NOW()
           WHERE id=$1""",
        ticket_id, admin_note
    )

async def count_open_tickets() -> int:
    return await get_pool().fetchval(
        "SELECT COUNT(*) FROM support_tickets WHERE status='open'"
    )


# ═══════════════════════════════════════════════════════════════
# AI REPORTS
# ═══════════════════════════════════════════════════════════════

async def save_ai_report(business_id: int, rtype: str, content: str):
    await get_pool().execute(
        "INSERT INTO ai_reports (business_id,type,content) VALUES ($1,$2,$3)",
        business_id, rtype, content
    )

async def get_recent_ai_reports(business_id: int, rtype: str = None,
                                 limit: int = 5) -> list:
    if rtype:
        return await get_pool().fetch(
            """SELECT * FROM ai_reports WHERE business_id=$1 AND type=$2
               ORDER BY created_at DESC LIMIT $3""",
            business_id, rtype, limit
        )
    return await get_pool().fetch(
        """SELECT * FROM ai_reports WHERE business_id=$1
           ORDER BY created_at DESC LIMIT $2""",
        business_id, limit
    )


# ═══════════════════════════════════════════════════════════════
# WAREHOUSE — PRODUCTS
# ═══════════════════════════════════════════════════════════════

async def create_category(business_id: int, name: str) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO product_categories (business_id,name)
           VALUES ($1,$2) RETURNING id""",
        business_id, name
    )
    return row["id"]

async def get_categories(business_id: int) -> list:
    return await get_pool().fetch(
        "SELECT * FROM product_categories WHERE business_id=$1 ORDER BY name",
        business_id
    )

async def create_product(business_id: int, category_id: int, name: str,
                          unit: str = "шт", min_stock: float = 0) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO products (business_id,category_id,name,unit,min_stock)
           VALUES ($1,$2,$3,$4,$5) RETURNING id""",
        business_id, category_id, name, unit, min_stock
    )
    return row["id"]

async def get_products(business_id: int, category_id: int = None) -> list:
    if category_id:
        return await get_pool().fetch(
            """SELECT p.*,pc.name as category_name FROM products p
               LEFT JOIN product_categories pc ON pc.id=p.category_id
               WHERE p.business_id=$1 AND p.category_id=$2 AND p.is_active=TRUE
               ORDER BY p.name""",
            business_id, category_id
        )
    return await get_pool().fetch(
        """SELECT p.*,pc.name as category_name FROM products p
           LEFT JOIN product_categories pc ON pc.id=p.category_id
           WHERE p.business_id=$1 AND p.is_active=TRUE ORDER BY p.name""",
        business_id
    )

async def get_product(product_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        "SELECT * FROM products WHERE id=$1", product_id
    )

async def update_product_stock(product_id: int, delta: float):
    await get_pool().execute(
        "UPDATE products SET current_stock=current_stock+$2 WHERE id=$1",
        product_id, delta
    )

async def get_low_stock_products(business_id: int) -> list:
    return await get_pool().fetch(
        """SELECT * FROM products
           WHERE business_id=$1 AND is_active=TRUE
             AND current_stock<=min_stock AND min_stock>0""",
        business_id
    )


# ═══════════════════════════════════════════════════════════════
# WAREHOUSE — SUPPLIERS
# ═══════════════════════════════════════════════════════════════

async def create_supplier(business_id: int, name: str,
                           phone: str = "", comment: str = "") -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO suppliers (business_id,name,phone,comment)
           VALUES ($1,$2,$3,$4) RETURNING id""",
        business_id, name, phone, comment
    )
    return row["id"]

async def get_suppliers(business_id: int) -> list:
    return await get_pool().fetch(
        "SELECT * FROM suppliers WHERE business_id=$1 ORDER BY name",
        business_id
    )


# ═══════════════════════════════════════════════════════════════
# WAREHOUSE — DELIVERIES
# ═══════════════════════════════════════════════════════════════

async def create_delivery(business_id: int, location_id: int,
                           supplier_id: int, created_by: int,
                           expected_at: str = None, comment: str = "") -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO deliveries
           (business_id,location_id,supplier_id,created_by,expected_at,comment)
           VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
        business_id, location_id, supplier_id, created_by, expected_at, comment
    )
    return row["id"]

async def add_delivery_item(delivery_id: int, product_id: int,
                             expected_qty: float) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO delivery_items (delivery_id,product_id,expected_quantity)
           VALUES ($1,$2,$3) RETURNING id""",
        delivery_id, product_id, expected_qty
    )
    return row["id"]

async def get_deliveries(business_id: int, status: str = None) -> list:
    if status:
        return await get_pool().fetch(
            """SELECT d.*,s.name as supplier_name,l.name as location_name
               FROM deliveries d
               LEFT JOIN suppliers s ON s.id=d.supplier_id
               LEFT JOIN locations l ON l.id=d.location_id
               WHERE d.business_id=$1 AND d.status=$2
               ORDER BY d.created_at DESC""",
            business_id, status
        )
    return await get_pool().fetch(
        """SELECT d.*,s.name as supplier_name,l.name as location_name
           FROM deliveries d
           LEFT JOIN suppliers s ON s.id=d.supplier_id
           LEFT JOIN locations l ON l.id=d.location_id
           WHERE d.business_id=$1 ORDER BY d.created_at DESC LIMIT 20""",
        business_id
    )

async def get_delivery(delivery_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        """SELECT d.*,s.name as supplier_name FROM deliveries d
           LEFT JOIN suppliers s ON s.id=d.supplier_id WHERE d.id=$1""",
        delivery_id
    )

async def get_delivery_items(delivery_id: int) -> list:
    return await get_pool().fetch(
        """SELECT di.*,p.name as product_name,p.unit FROM delivery_items di
           JOIN products p ON p.id=di.product_id
           WHERE di.delivery_id=$1""",
        delivery_id
    )

async def receive_delivery_item(item_id: int, actual_qty: float,
                                  comment: str = ""):
    row = await get_pool().fetchrow(
        "SELECT expected_quantity FROM delivery_items WHERE id=$1", item_id
    )
    discrepancy = actual_qty - float(row["expected_quantity"]) if row else 0
    await get_pool().execute(
        """UPDATE delivery_items SET actual_quantity=$2,discrepancy=$3,comment=$4
           WHERE id=$1""",
        item_id, actual_qty, discrepancy, comment
    )

async def complete_delivery(delivery_id: int, received_by: int):
    await get_pool().execute(
        """UPDATE deliveries SET status='received',received_at=NOW(),received_by=$2
           WHERE id=$1""",
        delivery_id, received_by
    )

async def get_expected_deliveries(location_id: int) -> list:
    return await get_pool().fetch(
        """SELECT d.*,s.name as supplier_name FROM deliveries d
           LEFT JOIN suppliers s ON s.id=d.supplier_id
           WHERE d.location_id=$1 AND d.status='expected'
           ORDER BY d.expected_at""",
        location_id
    )


# ═══════════════════════════════════════════════════════════════
# WAREHOUSE — INVENTORY
# ═══════════════════════════════════════════════════════════════

async def create_inventory_session(business_id: int, location_id: int,
                                    started_by: int) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO inventory_sessions (business_id,location_id,started_by)
           VALUES ($1,$2,$3) RETURNING id""",
        business_id, location_id, started_by
    )
    return row["id"]

async def add_inventory_item(session_id: int, product_id: int,
                              expected_qty: float) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO inventory_items
           (inventory_session_id,product_id,expected_quantity)
           VALUES ($1,$2,$3) RETURNING id""",
        session_id, product_id, expected_qty
    )
    return row["id"]

async def update_inventory_item(item_id: int, actual_qty: float,
                                  comment: str = ""):
    row = await get_pool().fetchrow(
        "SELECT expected_quantity FROM inventory_items WHERE id=$1", item_id
    )
    discrepancy = actual_qty - float(row["expected_quantity"]) if row else 0
    await get_pool().execute(
        """UPDATE inventory_items
           SET actual_quantity=$2, discrepancy=$3, status='counted', comment=$4
           WHERE id=$1""",
        item_id, actual_qty, discrepancy, comment
    )

async def complete_inventory(session_id: int, completed_by: int,
                               comment: str = ""):
    await get_pool().execute(
        """UPDATE inventory_sessions SET status='completed',completed_by=$2,
           completed_at=NOW(),comment=$3 WHERE id=$1""",
        session_id, completed_by, comment
    )

async def get_inventory_session(session_id: int) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(
        "SELECT * FROM inventory_sessions WHERE id=$1", session_id
    )

async def get_inventory_items(session_id: int) -> list:
    return await get_pool().fetch(
        """SELECT ii.*,p.name as product_name,p.unit FROM inventory_items ii
           JOIN products p ON p.id=ii.product_id
           WHERE ii.inventory_session_id=$1 ORDER BY p.name""",
        session_id
    )


# ═══════════════════════════════════════════════════════════════
# STOCK MOVEMENTS & ALERTS
# ═══════════════════════════════════════════════════════════════

async def add_stock_movement(business_id: int, location_id: int,
                              product_id: int, mtype: str, quantity: float,
                              source_type: str = "manual", source_id: int = None,
                              comment: str = "", created_by: int = None):
    await get_pool().execute(
        """INSERT INTO stock_movements
           (business_id,location_id,product_id,type,quantity,
            source_type,source_id,comment,created_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
        business_id, location_id, product_id, mtype, quantity,
        source_type, source_id, comment, created_by
    )
    await update_product_stock(product_id, quantity)

async def create_stock_alert(business_id: int, location_id: int,
                              product_id: int, alert_type: str,
                              message: str) -> int:
    row = await get_pool().fetchrow(
        """INSERT INTO stock_alerts
           (business_id,location_id,product_id,type,message)
           VALUES ($1,$2,$3,$4,$5) RETURNING id""",
        business_id, location_id, product_id, alert_type, message
    )
    return row["id"]

async def get_open_stock_alerts(business_id: int) -> list:
    return await get_pool().fetch(
        """SELECT sa.*,p.name as product_name FROM stock_alerts sa
           LEFT JOIN products p ON p.id=sa.product_id
           WHERE sa.business_id=$1 AND sa.status='open'
           ORDER BY sa.created_at DESC""",
        business_id
    )

async def get_unclosed_shifts_yesterday() -> list:
    """Незакрытые смены за вчера — для health check."""
    from datetime import date, timedelta
    yesterday = date.today() - timedelta(days=1)
    return await get_pool().fetch(
        """SELECT s.*,l.name as loc_name,b.name as biz_name
           FROM shifts s
           JOIN locations l ON l.id=s.location_id
           JOIN businesses b ON b.id=s.business_id
           WHERE s.status='open' AND s.date=$1""",
        yesterday
    )

async def get_stuck_payments() -> list:
    """Платежи в статусе pending больше 1 часа."""
    return await get_pool().fetch(
        """SELECT * FROM payments
           WHERE status='pending'
           AND created_at < NOW() - INTERVAL '1 hour'"""
    )

async def get_businesses_without_owner() -> list:
    return await get_pool().fetch(
        """SELECT b.* FROM businesses b
           WHERE NOT EXISTS (
               SELECT 1 FROM users u WHERE u.telegram_id=b.owner_id
           )"""
    )

async def touch_business(bid: int):
    await get_pool().execute(
        "UPDATE businesses SET last_active_at=NOW() WHERE id=$1", bid
    )

async def get_open_anomalies(business_id: int, severity: str = None) -> list:
    """Открытые аномалии бизнеса."""
    if severity:
        rows = await get_pool().fetch(
            """SELECT * FROM anomalies WHERE business_id=$1
               AND severity=$2 AND status='open'
               ORDER BY created_at DESC LIMIT 20""",
            business_id, severity
        )
    else:
        rows = await get_pool().fetch(
            """SELECT * FROM anomalies WHERE business_id=$1
               AND status='open' ORDER BY created_at DESC LIMIT 20""",
            business_id
        )
    return [dict(r) for r in rows]
