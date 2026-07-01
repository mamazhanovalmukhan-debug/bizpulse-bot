"""Бизнес-логика смен v6 — исправлены дубли cash_movements."""
from datetime import date
from database.models import (
    open_shift, close_shift_db, add_movement,
    get_shift_movements, save_shift_report, save_cash_check
)
from services.cash_service import (
    calc_expected_cash, validate_cash_report,
    check_discrepancy, format_cash_summary, format_owner_alert
)
from utils.formatting import fmt_money


async def start_shift(business_id: int, location_id: int, user_id: int,
                      opening_cash: float, comment: str = "") -> int:
    return await open_shift(business_id, location_id, user_id, opening_cash, comment)


async def record_expense(shift_id: int, business_id: int, location_id: int,
                         amount: float, comment: str, user_id: int = None):
    await add_movement(business_id, location_id, shift_id,
                       "expense", amount, comment, user_id)


async def record_collection(shift_id: int, business_id: int, location_id: int,
                             amount: float, comment: str = "", user_id: int = None):
    await add_movement(business_id, location_id, shift_id,
                       "collection", amount, comment, user_id)


async def record_refund(shift_id: int, business_id: int, location_id: int,
                        amount: float, comment: str = "", user_id: int = None):
    await add_movement(business_id, location_id, shift_id,
                       "refund", amount, comment, user_id)


async def record_deposit(shift_id: int, business_id: int, location_id: int,
                          amount: float, comment: str = "", user_id: int = None):
    await add_movement(business_id, location_id, shift_id,
                       "deposit", amount, comment, user_id)


def _sum_movements(movements: list, mtype: str) -> float:
    return sum(float(m["amount"]) for m in movements if m["type"] == mtype)


async def get_shift_totals(shift_id: int, opening_cash: float) -> dict:
    """Считает все итоги смены из уже записанных cash_movements."""
    movs = await get_shift_movements(shift_id)
    cash_sales  = _sum_movements(movs, "sale_cash")
    card_sales  = _sum_movements(movs, "sale_card")
    agg_sales   = _sum_movements(movs, "sale_sbp")
    expenses    = _sum_movements(movs, "expense")
    refunds     = _sum_movements(movs, "refund")
    collection  = _sum_movements(movs, "collection")
    deposits    = _sum_movements(movs, "deposit")
    cash_exp    = calc_expected_cash(
        opening_cash, cash_sales, expenses, refunds, collection, deposits
    )
    return {
        "cash_sales": cash_sales, "card_sales": card_sales,
        "aggregator_sales": agg_sales,
        "total_sales": cash_sales + card_sales + agg_sales,
        "expenses": expenses, "refunds": refunds,
        "collection": collection, "deposits": deposits,
        "cash_expected": cash_exp,
    }


async def do_interim_check(
        shift_id: int, business_id: int, location_id: int,
        opening_cash: float, actual_cash: float, user_id: int,
        location_name: str = "", employee_name: str = "") -> tuple:
    """
    Промежуточная проверка кассы на основе уже записанных движений.
    Возвращает (employee_msg, owner_alert_or_None, discrepancy_dict)
    """
    totals   = await get_shift_totals(shift_id, opening_cash)
    cash_exp = totals["cash_expected"]

    discr = check_discrepancy(cash_exp, actual_cash)

    status_map = {
        "ok":      "ok",
        "warning": "ok",
        "alert":   "shortage" if discr["diff"] < 0 else "surplus",
    }
    await save_cash_check(
        business_id, location_id, shift_id,
        cash_exp, actual_cash, discr["diff"],
        status_map.get(discr["status"], "ok"), user_id
    )

    employee_msg = (
        "💰 ПРОМЕЖУТОЧНЫЙ ОТЧЁТ\n\n"
        + format_cash_summary(
            opening_cash,
            totals["cash_sales"], totals["card_sales"],
            totals["aggregator_sales"],
            totals["expenses"], totals["refunds"],
            totals["collection"], totals["deposits"],
            cash_exp, actual_cash
        )
        + (f"\n\n{discr['message']}" if discr["status"] != "ok"
           else "\n\n✅ Касса сходится.")
    )

    owner_alert = None
    if discr["status"] == "alert":
        owner_alert = format_owner_alert(
            discr["diff"], cash_exp, actual_cash,
            location_name, employee_name, str(date.today())
        )

    return employee_msg, owner_alert, discr


async def do_close_shift(
        shift_id: int, business_id: int, location_id: int,
        user_id: int, opening_cash: float,
        cash_sales: float, card_sales: float, aggregator_sales: float,
        expenses: float, refunds: float, collection: float,
        deposits: float, cash_actual: float,
        closing_comment: str, discrepancy_comment: str,
        location_name: str, employee_name: str) -> tuple:
    """
    Полное закрытие смены.

    ВАЖНО: add_movement() НЕ вызывается здесь для expenses/collection/refunds/deposits.
    Эти операции уже были записаны сотрудником через отдельные кнопки
    (🧾 Расход, 📤 Инкассация, ↩️ Возврат) в течение смены.

    Суммы из параметров используются ТОЛЬКО для sale_cash/sale_card/sale_sbp
    (выручка вводится только при закрытии, не через отдельные кнопки),
    и для формирования shift_report.

    Возвращает (result_dict, owner_alert_or_None)
    """
    # Записываем ТОЛЬКО продажи — они вводятся впервые при закрытии
    if cash_sales        > 0:
        await add_movement(business_id, location_id, shift_id,
                           "sale_cash", cash_sales, "", user_id)
    if card_sales        > 0:
        await add_movement(business_id, location_id, shift_id,
                           "sale_card", card_sales, "", user_id)
    if aggregator_sales  > 0:
        await add_movement(business_id, location_id, shift_id,
                           "sale_sbp", aggregator_sales, "", user_id)

    # Считаем итоги из ВСЕХ движений за смену (включая записанные ранее)
    totals = await get_shift_totals(shift_id, opening_cash)

    # Пересчитываем ожидаемый остаток по реальным данным из БД
    cash_expected = totals["cash_expected"]
    discr = check_discrepancy(cash_expected, cash_actual)

    total_sales = totals["total_sales"]

    # Сохраняем итоговый shift_report
    await save_shift_report(
        shift_id=shift_id,
        report_type="closing",
        cash_start=opening_cash,
        cash_sales=totals["cash_sales"],
        card_sales=totals["card_sales"],
        aggregator_sales=totals["aggregator_sales"],
        expenses=totals["expenses"],
        refunds=totals["refunds"],
        collection=totals["collection"],
        deposits=totals["deposits"],
        cash_expected=cash_expected,
        cash_actual=cash_actual,
        discrepancy=discr["diff"],
        discrepancy_comment=discrepancy_comment,
        created_by=user_id,
    )

    # Закрываем смену в БД
    await close_shift_db(shift_id, user_id, cash_actual, closing_comment)

    result = {
        "opening_cash":      opening_cash,
        "cash_sales":        totals["cash_sales"],
        "card_sales":        totals["card_sales"],
        "aggregator_sales":  totals["aggregator_sales"],
        "total_sales":       total_sales,
        "expenses":          totals["expenses"],
        "refunds":           totals["refunds"],
        "collection":        totals["collection"],
        "deposits":          totals["deposits"],
        "cash_expected":     cash_expected,
        "cash_actual":       cash_actual,
        "discrepancy":       discr["diff"],
        "discrepancy_status":  discr["status"],
        "discrepancy_message": discr["message"],
    }

    owner_alert = None
    if discr["status"] == "alert":
        owner_alert = format_owner_alert(
            discr["diff"], cash_expected, cash_actual,
            location_name, employee_name, str(date.today())
        )

    return result, owner_alert
