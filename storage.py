from datetime import datetime, date
from collections import defaultdict
from config import MSK

_reports: dict[date, list[dict]] = defaultdict(list)

# Последний зафиксированный остаток в кассе
_last_cash_balance: float = 0.0

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
    reports = get_today_reports()
    total_cash = sum(r.get("cash", 0) for r in reports if r.get("type") == "closing")
    total_card = sum(r.get("card", 0) for r in reports if r.get("type") == "closing")
    opened     = any(r.get("type") == "opening" for r in reports)
    closed     = any(r.get("type") == "closing" for r in reports)
    opening    = next((r for r in reports if r.get("type") == "opening"), None)
    return {
        "total_cash":    total_cash,
        "total_card":    total_card,
        "total":         total_cash + total_card,
        "opened":        opened,
        "closed":        closed,
        "reports_count": len(reports),
        "opening":       opening,
    }

def get_yesterday_closing() -> dict | None:
    """Возвращает отчёт о закрытии за вчера."""
    yesterday = date.fromordinal(date.today().toordinal() - 1)
    reports = _reports.get(yesterday, [])
    return next((r for r in reports if r.get("type") == "closing"), None)

def set_last_cash_balance(amount: float):
    global _last_cash_balance
    _last_cash_balance = amount

def get_last_cash_balance() -> float:
    return _last_cash_balance

def get_expected_cash(opening_cash: float, interim_sales: float = 0) -> float:
    """Минимальный ожидаемый остаток наличных."""
    return opening_cash + interim_sales
