from datetime import datetime, date
from collections import defaultdict
from config import MSK

_reports: dict[date, list[dict]] = defaultdict(list)

# Состояние кассы за текущий день
_cash_state = {
    "opening":      0.0,   # касса на открытие
    "last_interim": 0.0,   # последний зафиксированный остаток (открытие или промежуток)
    "total_expenses": 0.0, # сумма расходов за день
}

# Поставки: { id: {info} }
_deliveries: dict[str, dict] = {}

def reset_cash_state():
    _cash_state["opening"]       = 0.0
    _cash_state["last_interim"]  = 0.0
    _cash_state["total_expenses"] = 0.0

def set_opening_cash(amount: float):
    _cash_state["opening"]      = amount
    _cash_state["last_interim"] = amount

def get_opening_cash() -> float:
    return _cash_state["opening"]

def get_last_interim_cash() -> float:
    return _cash_state["last_interim"]

def update_interim_cash(amount: float, expenses: float = 0.0):
    """Обновляем последний известный остаток и накапливаем расходы."""
    _cash_state["last_interim"]   = amount
    _cash_state["total_expenses"] += expenses

def get_expected_closing_balance(cash_revenue: float, closing_expenses: float = 0.0) -> float:
    """Ожидаемый остаток на закрытии = открытие + выручка нал - все расходы."""
    return (
        _cash_state["opening"]
        + cash_revenue
        - _cash_state["total_expenses"]
        - closing_expenses
    )

def save_report(report: dict):
    today = date.today()
    report["saved_at"] = datetime.now(MSK).isoformat()
    _reports[today].append(report)

def get_today_reports() -> list[dict]:
    return _reports.get(date.today(), [])

def get_week_reports() -> list[dict]:
    today = date.today()
    result = []
    for d, reports in _reports.items():
        if (today - d).days <= 7:
            result.extend(reports)
    return result

def get_all_stock_notes() -> list[str]:
    notes = []
    for reports in _reports.values():
        for r in reports:
            note = r.get("stock_notes", "")
            if note and note not in ("Пропустить", "Без замечаний", ""):
                notes.append(note)
    return notes

def get_today_summary() -> dict:
    reports  = get_today_reports()
    closings = [r for r in reports if r.get("type") == "closing"]
    total_cash = sum(r.get("cash", 0) for r in closings)
    total_card = sum(r.get("card", 0) for r in closings)
    opened     = any(r.get("type") == "opening" for r in reports)
    closed     = any(r.get("type") == "closing" for r in reports)
    return {
        "total_cash":    total_cash,
        "total_card":    total_card,
        "total":         total_cash + total_card,
        "opened":        opened,
        "closed":        closed,
        "reports_count": len(reports),
    }

def get_yesterday_closing() -> dict | None:
    yesterday = date.fromordinal(date.today().toordinal() - 1)
    reports   = _reports.get(yesterday, [])
    return next((r for r in reports if r.get("type") == "closing"), None)

# ─── Поставки ────────────────────────────────────────────────────────────────

def add_delivery(delivery_id: str, info: dict):
    _deliveries[delivery_id] = info

def get_delivery(delivery_id: str) -> dict | None:
    return _deliveries.get(delivery_id)

def update_delivery(delivery_id: str, updates: dict):
    if delivery_id in _deliveries:
        _deliveries[delivery_id].update(updates)

def get_all_deliveries() -> dict:
    return _deliveries

def cancel_delivery(delivery_id: str):
    if delivery_id in _deliveries:
        _deliveries[delivery_id]["status"] = "cancelled"
