"""Кассовая логика v3 — строгая валидация по всем правилам."""
from config import config
from utils.formatting import fmt_money


def calc_expected_cash(cash_start: float, cash_sales: float = 0,
                        expenses: float = 0, refunds: float = 0,
                        collection: float = 0, deposits: float = 0) -> float:
    """
    cash_expected_end = cash_start + cash_sales - expenses - refunds
                        - collection + deposits
    """
    return cash_start + cash_sales - expenses - refunds - collection + deposits


def validate_cash_report(cash_start: float, cash_sales: float = 0,
                          expenses: float = 0, refunds: float = 0,
                          collection: float = 0, deposits: float = 0,
                          cash_actual: float = None) -> list:
    """
    Возвращает список ошибок. Пустой список = всё корректно.
    """
    errors = []
    available = cash_start + cash_sales + deposits

    # 1. Наличные не могут быть отрицательными
    if cash_start < 0:
        errors.append("Касса на начало смены не может быть отрицательной.")
    if cash_actual is not None and cash_actual < 0:
        errors.append("Остаток кассы не может быть отрицательным.")

    # 2. Расходы не превышают доступные наличные
    if expenses > available:
        errors.append(
            f"Расходы ({fmt_money(expenses)}) превышают доступные наличные "
            f"({fmt_money(available)}). Проверьте данные."
        )

    # 3. Инкассация не превышает доступные наличные
    if collection > available:
        errors.append(
            f"Инкассация ({fmt_money(collection)}) превышает доступные наличные "
            f"({fmt_money(available)}). Проверьте данные."
        )

    # 4. Возвраты не превышают доступные наличные
    if refunds > available:
        errors.append(
            f"Возвраты ({fmt_money(refunds)}) превышают доступные наличные "
            f"({fmt_money(available)}). Проверьте данные."
        )

    # 5. Если нет расходов/возвратов/инкассации — остаток ≥ начального
    if cash_actual is not None:
        if expenses == 0 and refunds == 0 and collection == 0:
            if cash_actual < cash_start:
                errors.append(
                    "Остаток кассы не может быть меньше начального, "
                    "если не было расходов, возвратов или инкассации. "
                    "Проверьте введённые данные."
                )

    return errors


def check_discrepancy(expected: float, actual: float) -> dict:
    """
    Возвращает: status (ok/warning/alert), diff, message
    """
    diff = actual - expected
    tolerance = config.CASH_TOLERANCE_AMOUNT

    if abs(diff) <= 1:
        return {"status": "ok", "diff": diff, "message": "✅ Касса сходится."}

    if abs(diff) <= tolerance:
        direction = "недостача" if diff < 0 else "излишек"
        return {
            "status": "warning",
            "diff": diff,
            "message": (
                f"⚠️ Небольшое расхождение ({direction}: {fmt_money(abs(diff))}).\n"
                f"В пределах допустимого ({fmt_money(tolerance)})."
            )
        }

    direction = "Недостача" if diff < 0 else "Излишек"
    return {
        "status": "alert",
        "diff": diff,
        "message": (
            f"🚨 {direction}: {fmt_money(abs(diff))}\n\n"
            f"Расчётный остаток: {fmt_money(expected)}\n"
            f"Фактический остаток: {fmt_money(actual)}\n"
            f"Расхождение: {fmt_money(diff)}"
        )
    }


def format_cash_summary(cash_start: float, cash_sales: float = 0,
                         card_sales: float = 0, aggregator_sales: float = 0,
                         expenses: float = 0, refunds: float = 0,
                         collection: float = 0, deposits: float = 0,
                         cash_expected: float = None,
                         cash_actual: float = None) -> str:
    total_revenue = cash_sales + card_sales + aggregator_sales
    lines = [
        f"💰 Касса на начало:    {fmt_money(cash_start)}",
        f"💵 Нал. продажи:       {fmt_money(cash_sales)}",
        f"💳 Эквайринг:          {fmt_money(card_sales)}",
        f"📱 Агрегаторы:         {fmt_money(aggregator_sales)}",
        f"📊 Итого выручка:      {fmt_money(total_revenue)}",
    ]
    if expenses > 0:
        lines.append(f"➖ Расходы:            {fmt_money(expenses)}")
    if refunds > 0:
        lines.append(f"↩️ Возвраты:           {fmt_money(refunds)}")
    if collection > 0:
        lines.append(f"🏦 Инкассация:         {fmt_money(collection)}")
    if deposits > 0:
        lines.append(f"➕ Внесения:           {fmt_money(deposits)}")
    if cash_expected is not None:
        lines.append(f"─────────────────────────")
        lines.append(f"📋 Ожидаемая касса:    {fmt_money(cash_expected)}")
    if cash_actual is not None:
        lines.append(f"💼 Фактическая касса:  {fmt_money(cash_actual)}")
    return "\n".join(lines)


def format_owner_alert(diff: float, expected: float, actual: float,
                        location_name: str, employee_name: str,
                        shift_date: str) -> str:
    direction = "НЕДОСТАЧА" if diff < 0 else "ИЗЛИШЕК"
    emoji = "🚨" if diff < 0 else "ℹ️"
    return (
        f"{emoji} {direction} ПО КАССЕ\n\n"
        f"Точка: {location_name}\n"
        f"Смена: {shift_date}\n"
        f"Сотрудник: {employee_name}\n\n"
        f"Ожидалось:   {fmt_money(expected)}\n"
        f"Фактически:  {fmt_money(actual)}\n"
        f"Расхождение: {fmt_money(diff)}"
    )
