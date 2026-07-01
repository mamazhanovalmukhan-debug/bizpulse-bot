"""Планировщик v3 — напоминания за 7/3/1/0 дней до окончания."""
import logging
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from aiogram import Bot
from database.models import (
    get_all_businesses, get_locations, get_open_shift,
    get_today_shifts, get_business_movements,
    get_all_stock_notes, get_low_stock_products,
    get_expiring_subs, get_trial_expiring,
    get_subscription, expire_subscription, get_business
)
from services.ai_service import analyze_day
from services.notification_service import (
    notify_owner, notify_location_employees,
    msg_opening_reminder, msg_shift_not_opened,
    msg_closing_reminder, msg_sub_expiring, msg_sub_expired
)
from services.plan_service import get_business_plan
from utils.formatting import fmt_money
from utils.dates import now_utc

log = logging.getLogger(__name__)


def _local_hour(tz_name: str) -> int:
    try:
        return datetime.now(ZoneInfo(tz_name)).hour
    except Exception:
        return datetime.now(ZoneInfo("Europe/Moscow")).hour


async def _is_sub_ok(business_id: int) -> bool:
    sub = await get_subscription(business_id)
    return bool(sub and sub["status"] in ("trial", "active"))


# ── Каждый час: проверки по точкам ──────────────────────────────────────────

async def job_hourly_location_checks(bot: Bot):
    businesses = await get_all_businesses()
    for biz in businesses:
        if biz["is_blocked"]:
            continue
        if not await _is_sub_ok(biz["id"]):
            continue
        locs = await get_locations(biz["id"])
        for loc in locs:
            tz     = loc.get("timezone") or "Europe/Moscow"
            hour   = _local_hour(tz)
            open_h = loc["open_time"]
            close_h = loc["close_time"]
            loc_id = loc["id"]

            if hour == open_h:
                await notify_location_employees(
                    bot, loc_id, msg_opening_reminder(loc["name"])
                )
            if hour == (open_h + 1) % 24:
                shift = await get_open_shift(loc_id)
                if not shift:
                    await notify_owner(bot, biz["owner_id"],
                                       msg_shift_not_opened(loc["name"]))
            if hour == (close_h - 1) % 24:
                shift = await get_open_shift(loc_id)
                if shift:
                    await notify_location_employees(
                        bot, loc_id, msg_closing_reminder(loc["name"])
                    )
            if hour == (close_h + 1) % 24:
                await _daily_digest(bot, biz)


async def _daily_digest(bot: Bot, biz):
    try:
        shifts    = await get_today_shifts(biz["id"])
        movs      = await get_business_movements(biz["id"], days=1)
        notes     = await get_all_stock_notes(biz["id"])
        low_stock = await get_low_stock_products(biz["id"])
        if not shifts and not movs:
            return
        cash = sum(m["amount"] for m in movs if m["type"] == "sale_cash")
        card = sum(m["amount"] for m in movs if m["type"] == "sale_card")
        agg  = sum(m["amount"] for m in movs if m["type"] == "sale_sbp")
        exp  = sum(m["amount"] for m in movs if m["type"] == "expense")
        from database.models import get_today_reports
        reports = await get_today_reports(biz["id"])
        await bot.send_message(
            biz["owner_id"],
            f"📊 Дайджест дня — {biz['name']}\n\n"
            f"Нал: {fmt_money(cash)} · Безнал: {fmt_money(card)} · Агрег: {fmt_money(agg)}\n"
            f"Итого: {fmt_money(cash+card+agg)} · Расходы: {fmt_money(exp)}\n\n"
            f"Запрашиваю ИИ-анализ..."
        )
        result = await analyze_day(
            biz["id"], biz["name"], biz["category"],
            [dict(r) for r in reports], [dict(m) for m in movs],
            notes, [dict(p) for p in low_stock]
        )
        await bot.send_message(biz["owner_id"], f"🤖 ИИ-анализ дня\n\n{result}")
    except Exception as e:
        log.error(f"Daily digest biz={biz['id']}: {e}")


# ── Еженедельный дайджест (воскресенье) ─────────────────────────────────────

async def job_weekly_digest(bot: Bot):
    businesses = await get_all_businesses()
    for biz in businesses:
        if biz["is_blocked"] or not await _is_sub_ok(biz["id"]):
            continue
        try:
            from database.models import get_week_shifts, get_week_reports
            movs    = await get_business_movements(biz["id"], days=7)
            reports = await get_week_reports(biz["id"])
            if not movs:
                continue
            total = sum(m["amount"] for m in movs if m["type"].startswith("sale_"))
            from services.ai_service import analyze_week
            result = await analyze_week(biz["id"], biz["name"],
                                        [dict(r) for r in reports],
                                        [dict(m) for m in movs])
            await bot.send_message(
                biz["owner_id"],
                f"📅 Итоги недели — {biz['name']}\n"
                f"Выручка: {fmt_money(total)}\n\n{result}"
            )
        except Exception as e:
            log.error(f"Weekly digest biz={biz['id']}: {e}")


# ── Напоминания об окончании подписки: 7/3/1/0 дней ─────────────────────────

async def job_subscription_reminders(bot: Bot):
    for days in (7, 3, 1):
        for sub in await get_expiring_subs(days):
            try:
                await bot.send_message(
                    sub["owner_id"],
                    msg_sub_expiring(days, sub["biz_name"])
                    + "\n\nОплатить: /pay\nСменить тариф: /change_plan"
                )
            except Exception as e:
                log.warning(f"Sub reminder {e}")
        for sub in await get_trial_expiring(days):
            try:
                await bot.send_message(
                    sub["owner_id"],
                    msg_sub_expiring(days, sub["biz_name"])
                    + "\n\nОплатить: /pay"
                )
            except Exception as e:
                log.warning(f"Trial reminder {e}")


# ── Проверка истёкших подписок ───────────────────────────────────────────────

async def job_expire_subscriptions(bot: Bot):
    businesses = await get_all_businesses()
    now = now_utc()
    for biz in businesses:
        sub = await get_subscription(biz["id"])
        if not sub:
            continue
        expired = False
        if sub["status"] == "trial" and sub["trial_ends_at"]:
            if now > sub["trial_ends_at"].replace(tzinfo=timezone.utc):
                await expire_subscription(biz["id"])
                expired = True
        elif sub["status"] == "active" and sub["current_period_end"]:
            if now > sub["current_period_end"].replace(tzinfo=timezone.utc):
                await expire_subscription(biz["id"])
                expired = True
        if expired:
            try:
                await bot.send_message(
                    biz["owner_id"], msg_sub_expired(biz["name"])
                )
            except Exception:
                pass


# ── Ночной health check ───────────────────────────────────────────────────────

async def job_nightly_health_check(bot: Bot):
    """Каждую ночь проверяет состояние системы и отправляет отчёт админам."""
    from config import config
    from database.models import (
        get_unclosed_shifts_yesterday, get_stuck_payments,
        get_businesses_without_owner, get_all_businesses
    )
    from services.anomaly_service import run_anomaly_check
    issues = []

    try:
        unclosed = await get_unclosed_shifts_yesterday()
        if unclosed:
            issues.append(f"🔴 Незакрытые смены вчера: {len(unclosed)}\n"
                         + "\n".join(f"  • {r['biz_name']} / {r['loc_name']}"
                                     for r in unclosed[:5]))
    except Exception as e:
        log.error(f"Health check unclosed: {e}")

    try:
        stuck = await get_stuck_payments()
        if stuck:
            issues.append(f"🔴 Зависшие платежи: {len(stuck)}")
    except Exception as e:
        log.error(f"Health check payments: {e}")

    try:
        no_owner = await get_businesses_without_owner()
        if no_owner:
            issues.append(f"⚠️ Бизнесы без владельца: {len(no_owner)}")
    except Exception as e:
        log.error(f"Health check no_owner: {e}")

    # Аномалии по каждому бизнесу
    try:
        businesses = await get_all_businesses()
        total_anomalies = 0
        for biz in businesses:
            if not biz["is_blocked"]:
                found = await run_anomaly_check(biz["id"], biz["name"])
                total_anomalies += len(found)
        if total_anomalies:
            issues.append(f"⚠️ Новых аномалий: {total_anomalies}")
    except Exception as e:
        log.error(f"Health check anomalies: {e}")

    report = "🔧 НОЧНОЙ HEALTH CHECK\n\n"
    if issues:
        report += "\n\n".join(issues)
    else:
        report += "✅ Всё в порядке."

    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, report)
        except Exception as e:
            log.warning(f"Health check notify admin {admin_id}: {e}")


async def job_morning_advisor(bot: Bot):
    """Утренние рекомендации от Business Advisor — каждый день в 07:00 МСК."""
    from services.advisor_service import generate_daily_advice, compute_health_score, format_health_score
    businesses = await get_all_businesses()
    for biz in businesses:
        if biz["is_blocked"] or not await _is_sub_ok(biz["id"]):
            continue
        try:
            advice = await generate_daily_advice(biz["id"], biz["name"], biz["category"])
            await bot.send_message(biz["owner_id"], advice)
            # Health Score раз в день
            from config import config
            if config.HEALTH_SCORE_ENABLED:
                hs = await compute_health_score(biz["id"])
                if hs["score"] < 80 or hs.get("issues"):
                    await bot.send_message(
                        biz["owner_id"],
                        format_health_score(hs, biz["name"])
                    )
        except Exception as e:
            log.error(f"Morning advisor biz={biz['id']}: {e}")
