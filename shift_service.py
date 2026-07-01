"""Аналитика сотрудников и бизнеса."""
import logging
from database.models import (
    get_employee_shifts, get_shift_reports,
    get_today_reports, get_week_reports,
    get_business_users, get_business_movements
)
from utils.formatting import fmt_money
from config import config


async def get_employee_stats(user_id: int, business_id: int,
                              employee_name: str, days: int = 30) -> str:
    shifts = await get_employee_shifts(user_id, business_id, days)
    count = len(shifts)

    if count < config.MIN_SHIFTS_FOR_ANALYTICS:
        return (
            f"👤 Сотрудник: {employee_name}\n"
            f"Смен за {days} дней: {count}\n\n"
            f"Пока недостаточно данных для объективной оценки. "
            f"Нужно минимум {config.MIN_SHIFTS_FOR_ANALYTICS} смен."
        )

    # Собираем выручку по сменам
    revenues = []
    discrepancies = 0
    for shift in shifts:
        reports = await get_shift_reports(shift["id"])
        closing = next((r for r in reports if r["report_type"] == "closing"), None)
        if closing:
            rev = (closing["cash_sales"] or 0) + (closing["card_sales"] or 0) + \
                  (closing["aggregator_sales"] or 0)
            revenues.append(rev)
            if closing["discrepancy"] and abs(closing["discrepancy"]) > 10:
                discrepancies += 1

    if not revenues:
        return f"👤 {employee_name}: смены есть, но отчётов о закрытии нет."

    avg_rev = sum(revenues) / len(revenues)
    max_rev = max(revenues)
    min_rev = min(revenues)

    lines = [
        f"👤 Аналитика: {employee_name}",
        f"Период: {days} дней · Смен: {count}",
        f"─────────────────────",
        f"Ср. выручка/смена:  {fmt_money(avg_rev)}",
        f"Лучшая смена:       {fmt_money(max_rev)}",
        f"Слабая смена:       {fmt_money(min_rev)}",
        f"Расхождений кассы:  {discrepancies}",
    ]
    return "\n".join(lines)


async def compare_employees(business_id: int, days: int = 30) -> str:
    users = await get_business_users(business_id)
    employees = [u for u in users if u["role"] == "employee"]
    if len(employees) < 2:
        return "Для сравнения нужно минимум 2 сотрудника."

    stats = []
    for emp in employees:
        shifts = await get_employee_shifts(emp["user_id"], business_id, days)
        if len(shifts) < config.MIN_SHIFTS_FOR_ANALYTICS:
            continue
        revenues = []
        for shift in shifts:
            reports = await get_shift_reports(shift["id"])
            closing = next((r for r in reports if r["report_type"] == "closing"), None)
            if closing:
                rev = (closing["cash_sales"] or 0) + (closing["card_sales"] or 0) + \
                      (closing["aggregator_sales"] or 0)
                revenues.append(rev)
        if revenues:
            stats.append({
                "name": emp["full_name"],
                "avg": sum(revenues) / len(revenues),
                "shifts": len(revenues),
            })

    if not stats:
        return "Недостаточно данных для сравнения сотрудников."

    overall_avg = sum(s["avg"] for s in stats) / len(stats)
    stats.sort(key=lambda x: x["avg"], reverse=True)

    lines = [f"👥 Сравнение сотрудников (за {days} дней)\n"]
    for i, s in enumerate(stats):
        pct = ((s["avg"] - overall_avg) / overall_avg * 100) if overall_avg else 0
        sign = "+" if pct >= 0 else ""
        medal = ["🥇", "🥈", "🥉"].get(i, "  ") if i < 3 else "  "
        lines.append(
            f"{medal} {s['name']}: {fmt_money(s['avg'])}/смена "
            f"({sign}{pct:.0f}% от среднего)"
        )
    lines.append(f"\nСредняя по бизнесу: {fmt_money(overall_avg)}/смена")

    # Выявляем слабых
    for s in stats:
        pct = ((s["avg"] - overall_avg) / overall_avg * 100) if overall_avg else 0
        if pct < -20 and s["shifts"] >= config.MIN_SHIFTS_FOR_ANALYTICS:
            lines.append(
                f"\n⚠️ {s['name']} показывает выручку на {abs(pct):.0f}% "
                f"ниже средней по точке за сопоставимые смены. "
                f"Рекомендуется проверить."
            )
    return "\n".join(lines)


async def get_daily_summary(business_id: int, biz_name: str) -> str:
    reports = await get_today_reports(business_id)
    if not reports:
        return f"За сегодня отчётов ещё нет."

    cash_total = sum(r["cash_sales"] or 0 for r in reports if r["report_type"] == "closing")
    card_total = sum(r["card_sales"] or 0 for r in reports if r["report_type"] == "closing")
    agg_total  = sum(r["aggregator_sales"] or 0 for r in reports if r["report_type"] == "closing")
    exp_total  = sum(r["expenses"] or 0 for r in reports if r["report_type"] == "closing")
    discr      = [r for r in reports if r.get("discrepancy") and abs(r["discrepancy"]) > 10]
    total_rev  = cash_total + card_total + agg_total

    lines = [
        f"📊 Итоги дня — {biz_name}",
        f"─────────────────────",
        f"💵 Нал:         {fmt_money(cash_total)}",
        f"💳 Эквайринг:   {fmt_money(card_total)}",
        f"📱 Агрегаторы:  {fmt_money(agg_total)}",
        f"📊 Итого:       {fmt_money(total_rev)}",
        f"➖ Расходы:     {fmt_money(exp_total)}",
    ]
    if discr:
        lines.append(f"⚠️ Расхождений кассы: {len(discr)}")
    return "\n".join(lines)
