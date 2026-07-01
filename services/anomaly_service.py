"""Детектор аномалий BizPulse — исправлены дубли (CRIT-2)."""
import logging
from datetime import date, timedelta
from database.session import get_pool
from database.models import get_low_stock_products
from utils.formatting import fmt_money

log = logging.getLogger("anomaly")

SEVERITY_INFO     = "info"
SEVERITY_WARNING  = "warning"
SEVERITY_CRITICAL = "critical"


async def _anomaly_open_exists(business_id: int, anomaly_type: str,
                                location_id: int = None) -> bool:
    """
    Проверяет, есть ли уже открытая аномалия того же типа для этого бизнеса
    за сегодняшний день. Предотвращает создание дублей при повторных запусках.
    """
    try:
        row = await get_pool().fetchrow(
            """SELECT id FROM anomalies
               WHERE business_id=$1
                 AND type=$2
                 AND status='open'
                 AND DATE(created_at)=CURRENT_DATE
                 AND ($3::int IS NULL OR location_id=$3)
               LIMIT 1""",
            business_id, anomaly_type, location_id
        )
        return row is not None
    except Exception as e:
        log.error(f"_anomaly_open_exists error: {e}")
        return False


async def save_anomaly(business_id: int, anomaly_type: str, severity: str,
                       title: str, description: str, recommendation: str = "",
                       location_id: int = None, user_id: int = None) -> int:
    """
    Создаёт аномалию. Проверяет дубли — не создаёт повторную открытую аномалию
    того же типа за тот же день.
    """
    if await _anomaly_open_exists(business_id, anomaly_type, location_id):
        return 0  # дубль — не создаём

    try:
        row = await get_pool().fetchrow(
            """INSERT INTO anomalies
               (business_id, location_id, user_id, type, severity,
                title, description, recommendation, status)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'open')
               RETURNING id""",
            business_id, location_id, user_id, anomaly_type, severity,
            title, description, recommendation
        )
        return row["id"] if row else 0
    except Exception as e:
        log.error(f"save_anomaly error: {e}")
        return 0


async def get_open_anomalies(business_id: int, severity: str = None) -> list:
    try:
        if severity:
            rows = await get_pool().fetch(
                """SELECT * FROM anomalies
                   WHERE business_id=$1 AND severity=$2 AND status='open'
                   ORDER BY created_at DESC LIMIT 20""",
                business_id, severity
            )
        else:
            rows = await get_pool().fetch(
                """SELECT * FROM anomalies
                   WHERE business_id=$1 AND status='open'
                   ORDER BY created_at DESC LIMIT 20""",
                business_id
            )
        return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"get_open_anomalies error: {e}")
        return []


async def resolve_anomaly(anomaly_id: int):
    try:
        await get_pool().execute(
            "UPDATE anomalies SET status='resolved', resolved_at=NOW() WHERE id=$1",
            anomaly_id
        )
    except Exception as e:
        log.error(f"resolve_anomaly error: {e}")


async def run_anomaly_check(business_id: int, biz_name: str) -> list:
    """
    Проверяет бизнес на аномалии. Каждый тип аномалии создаётся не более одного
    раза в день (дубли пропускаются через _anomaly_open_exists).
    """
    found = []

    # 1. Падение выручки > порога
    try:
        from config import config
        from database.models import get_week_reports
        reports = await get_week_reports(business_id)
        if len(reports) >= 2:
            def rev(r):
                return (float(r.get("cash_sales") or 0)
                        + float(r.get("card_sales") or 0)
                        + float(r.get("aggregator_sales") or 0))
            latest_rev = rev(reports[0])
            prev_revs  = [rev(r) for r in reports[1:]]
            avg_prev   = sum(prev_revs) / len(prev_revs) if prev_revs else 0
            if avg_prev > 0:
                drop_pct = (avg_prev - latest_rev) / avg_prev * 100
                if drop_pct > config.ANOMALY_DROP_PERCENT:
                    aid = await save_anomaly(
                        business_id, "revenue_drop", SEVERITY_WARNING,
                        f"Падение выручки на {drop_pct:.0f}%",
                        f"Выручка: {fmt_money(latest_rev)}, "
                        f"среднее: {fmt_money(avg_prev)}",
                        "Проверьте загрузку точки и работу сотрудников."
                    )
                    if aid:
                        found.append({"id": aid, "type": "revenue_drop",
                                      "severity": SEVERITY_WARNING})
    except Exception as e:
        log.error(f"Anomaly revenue_drop: {e}")

    # 2. Частые кассовые расхождения
    try:
        rows = await get_pool().fetch(
            """SELECT COUNT(*) as cnt FROM cash_checks
               WHERE business_id=$1
                 AND status IN ('shortage','surplus')
                 AND created_at >= NOW() - INTERVAL '7 days'""",
            business_id
        )
        cnt = int(rows[0]["cnt"]) if rows else 0
        if cnt >= 3:
            aid = await save_anomaly(
                business_id, "frequent_discrepancy", SEVERITY_WARNING,
                f"Частые расхождения кассы ({cnt} за 7 дней)",
                f"За последние 7 дней обнаружено {cnt} расхождений кассы.",
                "Проведите инвентаризацию кассы."
            )
            if aid:
                found.append({"id": aid, "type": "frequent_discrepancy",
                              "severity": SEVERITY_WARNING})
    except Exception as e:
        log.error(f"Anomaly discrepancy: {e}")

    # 3. Незакрытые смены вчера
    try:
        yesterday = date.today() - timedelta(days=1)
        rows = await get_pool().fetch(
            """SELECT s.id, l.name as loc_name, l.id as loc_id
               FROM shifts s
               JOIN locations l ON l.id=s.location_id
               WHERE s.business_id=$1 AND s.status='open' AND s.date=$2""",
            business_id, yesterday
        )
        for r in rows:
            aid = await save_anomaly(
                business_id, "unclosed_shift", SEVERITY_CRITICAL,
                f"Незакрытая смена: {r['loc_name']}",
                f"Смена от {yesterday} на точке «{r['loc_name']}» не закрыта.",
                "Свяжитесь с сотрудником.",
                location_id=r["loc_id"]
            )
            if aid:
                found.append({"id": aid, "type": "unclosed_shift",
                              "severity": SEVERITY_CRITICAL})
    except Exception as e:
        log.error(f"Anomaly unclosed_shift: {e}")

    # 4. Товары ниже минимального остатка
    try:
        low = await get_low_stock_products(business_id)
        for p in low:
            aid = await save_anomaly(
                business_id, f"low_stock_{p['id']}", SEVERITY_WARNING,
                f"Товар заканчивается: {p['name']}",
                f"{p['name']}: {p['current_stock']} {p['unit']} "
                f"(минимум: {p['min_stock']} {p['unit']})",
                "Оформите заказ у поставщика."
            )
            if aid:
                found.append({"id": aid, "type": f"low_stock_{p['id']}",
                              "severity": SEVERITY_WARNING})
    except Exception as e:
        log.error(f"Anomaly low_stock: {e}")

    # 5. Подозрительно большие суммы (> 500k за один movement)
    try:
        rows = await get_pool().fetch(
            """SELECT m.*, l.name as loc_name
               FROM cash_movements m
               LEFT JOIN locations l ON l.id=m.location_id
               WHERE m.business_id=$1
                 AND m.amount > 500000
                 AND m.created_at >= NOW() - INTERVAL '24 hours'""",
            business_id
        )
        for r in rows:
            aid = await save_anomaly(
                business_id, f"suspicious_amount_{r['id']}", SEVERITY_CRITICAL,
                f"Подозрительная сумма: {fmt_money(r['amount'])}",
                f"Тип: {r['type']}, точка: {r['loc_name']}, "
                f"сумма: {fmt_money(r['amount'])}",
                "Проверьте корректность введённых данных."
            )
            if aid:
                found.append({"id": aid, "type": f"suspicious_amount_{r['id']}",
                              "severity": SEVERITY_CRITICAL})
    except Exception as e:
        log.error(f"Anomaly suspicious_amount: {e}")

    return found


def format_anomalies_text(anomalies: list) -> str:
    if not anomalies:
        return "✅ Аномалий не обнаружено."
    severity_emoji = {
        SEVERITY_INFO:     "ℹ️",
        SEVERITY_WARNING:  "⚠️",
        SEVERITY_CRITICAL: "🚨",
    }
    lines = [f"Найдено аномалий: {len(anomalies)}\n"]
    for a in anomalies:
        e = severity_emoji.get(a.get("severity", "info"), "•")
        lines.append(
            f"{e} {a.get('title', '?')}\n"
            f"   {a.get('description', '')}"
        )
    return "\n\n".join(lines)
