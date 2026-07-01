"""Business Advisor — главный интеллект продукта. LOW-2: импорты на верхнем уровне."""
import logging
from datetime import date, timedelta, timezone

from database.models import (
    get_week_reports, get_business_movements,
    get_business_users, get_low_stock_products,
    get_employee_shifts, get_shift_reports,
    get_subscription, get_open_anomalies,
    get_all_stock_notes,
)
from database.session import get_pool
from services.subscription_service import check_subscription_status
from utils.formatting import fmt_money
from utils.dates import now_utc
from config import config

log = logging.getLogger("advisor")


async def generate_daily_advice(business_id: int, biz_name: str,
                                 biz_category: str) -> str:
    """
    Генерирует утренние рекомендации владельцу.
    Выводит рекомендации, а не цифры.
    """
    recommendations = []
    warnings        = []

    # 1. Незакрытые смены вчера
    try:
        yesterday = date.today() - timedelta(days=1)
        unclosed  = await get_pool().fetch(
            """SELECT l.name FROM shifts s
               JOIN locations l ON l.id=s.location_id
               WHERE s.business_id=$1 AND s.date=$2 AND s.status='open'""",
            business_id, yesterday
        )
        for r in unclosed:
            warnings.append(
                f"🔴 Смена на точке «{r['name']}» вчера не была закрыта."
            )
    except Exception as e:
        log.error(f"Advisor unclosed: {e}")

    # 2. Товары ниже минимума
    try:
        low = await get_low_stock_products(business_id)
        for p in low[:3]:
            recommendations.append(
                f"• Сегодня стоит заказать: {p['name']} "
                f"(осталось {p['current_stock']} {p['unit']})."
            )
    except Exception as e:
        log.error(f"Advisor low_stock: {e}")

    # 3. Аналитика сотрудников
    try:
        users     = await get_business_users(business_id)
        employees = [u for u in users if u["role"] == "employee"]
        emp_stats = []

        for emp in employees:
            shifts = await get_employee_shifts(emp["user_id"], business_id, 30)
            if len(shifts) < config.MIN_SHIFTS_FOR_ANALYTICS:
                continue
            revenues = []
            for s in shifts:
                rpts    = await get_shift_reports(s["id"])
                closing = next(
                    (r for r in rpts if r["report_type"] == "closing"), None
                )
                if closing:
                    rev = (float(closing.get("cash_sales") or 0)
                           + float(closing.get("card_sales") or 0)
                           + float(closing.get("aggregator_sales") or 0))
                    revenues.append(rev)
            if revenues:
                emp_stats.append({
                    "name":   emp["full_name"],
                    "avg":    sum(revenues) / len(revenues),
                    "shifts": len(revenues),
                })

        if len(emp_stats) >= 2:
            overall = sum(s["avg"] for s in emp_stats) / len(emp_stats)
            for s in emp_stats:
                pct = ((s["avg"] - overall) / overall * 100) if overall else 0
                if pct < -20:
                    recommendations.append(
                        f"• {s['name']} уже {s['shifts']} смен показывает выручку "
                        f"на {abs(pct):.0f}% ниже среднего — рекомендуется проверить."
                    )
    except Exception as e:
        log.error(f"Advisor employees: {e}")

    # 4. Падение выручки
    try:
        reports = await get_week_reports(business_id)
        if len(reports) >= 2:
            def rev(r):
                return (float(r.get("cash_sales") or 0)
                        + float(r.get("card_sales") or 0)
                        + float(r.get("aggregator_sales") or 0))

            latest_rev = rev(reports[0])
            prev_revs  = [rev(r) for r in reports[1:6]]
            avg_prev   = sum(prev_revs) / len(prev_revs) if prev_revs else 0

            if avg_prev > 0:
                drop = (avg_prev - latest_rev) / avg_prev * 100
                if drop > config.ANOMALY_DROP_PERCENT:
                    warnings.append(
                        f"⚠️ Вчера выручка была на {drop:.0f}% ниже средней "
                        f"— рекомендуется проверить вечернюю смену."
                    )

                # Рост расходов
                movs_today = await get_business_movements(business_id, 1)
                movs_week  = await get_business_movements(business_id, 7)
                today_exp  = sum(float(m["amount"]) for m in movs_today
                                 if m["type"] == "expense")
                prev_exp   = (sum(float(m["amount"]) for m in movs_week
                                  if m["type"] == "expense") / 7)
                if (prev_exp > 0
                        and today_exp > prev_exp
                        * (1 + config.ANOMALY_EXPENSE_PERCENT / 100)):
                    pct = (today_exp - prev_exp) / prev_exp * 100
                    warnings.append(
                        f"⚠️ Вчера расходы выросли на {pct:.0f}% — стоит проверить."
                    )
    except Exception as e:
        log.error(f"Advisor revenue: {e}")

    # 5. Подписка
    try:
        sub_status = await check_subscription_status(business_id)
        sub        = await get_subscription(business_id)
        if sub_status == "trial" and sub and sub.get("trial_ends_at"):
            days_left = (
                sub["trial_ends_at"].replace(tzinfo=timezone.utc) - now_utc()
            ).days
            if days_left <= 7:
                warnings.append(
                    f"⏰ Бесплатный период закончится через {days_left} дн. "
                    f"Оплатите для продолжения: /pay"
                )
    except Exception as e:
        log.error(f"Advisor subscription: {e}")

    # ── Формируем итог ────────────────────────────────────────────────────────
    if not recommendations and not warnings:
        return (
            f"🌅 Доброе утро!\n\n"
            f"Бизнес: {biz_name}\n\n"
            f"✅ Всё в порядке. Хорошего рабочего дня!"
        )

    lines = [f"🌅 Советник — {biz_name}\n"]
    if warnings:
        lines.append("Требует внимания:")
        lines.extend(warnings)
    if recommendations:
        if warnings:
            lines.append("")
        lines.append("Рекомендации на сегодня:")
        lines.extend(recommendations)

    return "\n".join(lines)


async def compute_health_score(business_id: int) -> dict:
    """Рассчитывает Health Score бизнеса (0-100)."""
    if not config.HEALTH_SCORE_ENABLED:
        return {"score": 0, "grade": "N/A", "issues": [], "details": "Отключено"}

    score  = 100
    issues = []

    try:
        # -15 за каждую незакрытую смену вчера
        yesterday = date.today() - timedelta(days=1)
        unclosed  = await get_pool().fetchval(
            """SELECT COUNT(*) FROM shifts
               WHERE business_id=$1 AND date=$2 AND status='open'""",
            business_id, yesterday
        )
        if unclosed:
            penalty = min(int(unclosed) * 15, 30)
            score  -= penalty
            issues.append(f"Незакрытые смены: {unclosed} (-{penalty})")

        # -5 за расхождения кассы (>2 за 7 дней)
        disc = await get_pool().fetchval(
            """SELECT COUNT(*) FROM cash_checks
               WHERE business_id=$1
                 AND status IN ('shortage','surplus')
                 AND created_at >= NOW() - INTERVAL '7 days'""",
            business_id
        )
        if disc and int(disc) > 2:
            penalty = min((int(disc) - 2) * 5, 20)
            score  -= penalty
            issues.append(f"Расхождения кассы: {disc} (-{penalty})")

        # -5 за каждый товар ниже минимума
        low = await get_low_stock_products(business_id)
        if low:
            penalty = min(len(low) * 5, 20)
            score  -= penalty
            issues.append(f"Товары ниже минимума: {len(low)} (-{penalty})")

        # -10 за критические аномалии
        critical = await get_open_anomalies(business_id, "critical")
        if critical:
            penalty = min(len(critical) * 10, 20)
            score  -= penalty
            issues.append(f"Критических аномалий: {len(critical)} (-{penalty})")

        # -3 за warning аномалии
        wrn = await get_open_anomalies(business_id, "warning")
        if wrn:
            penalty = min(len(wrn) * 3, 15)
            score  -= penalty
            issues.append(f"Предупреждений: {len(wrn)} (-{penalty})")

        # Подписка
        sub_status = await check_subscription_status(business_id)
        if sub_status == "expired":
            score -= 20
            issues.append("Подписка истекла (-20)")
        elif sub_status == "trial":
            sub = await get_subscription(business_id)
            if sub and sub.get("trial_ends_at"):
                days = (
                    sub["trial_ends_at"].replace(tzinfo=timezone.utc) - now_utc()
                ).days
                if days <= 3:
                    score -= 5
                    issues.append(f"Trial истекает через {days} дн. (-5)")

    except Exception as e:
        log.error(f"Health score error: {e}")
        score  = 50
        issues = ["Ошибка вычисления — используется базовая оценка"]

    score = max(0, min(100, score))

    if score >= 90:
        grade = "🟢 Отличное состояние"
    elif score >= 70:
        grade = "🟡 Хорошее состояние"
    elif score >= 50:
        grade = "🟠 Есть проблемы"
    else:
        grade = "🔴 Требует внимания"

    return {"score": score, "grade": grade, "issues": issues}


def format_health_score(hs: dict, biz_name: str = "") -> str:
    lines = [f"📊 HEALTH SCORE{f' — {biz_name}' if biz_name else ''}\n"]
    lines.append(f"{hs['score']}/100")
    lines.append(hs["grade"])
    if hs.get("issues"):
        lines.append("\nПроблемы:")
        for issue in hs["issues"]:
            lines.append(f"  • {issue}")
    return "\n".join(lines)
