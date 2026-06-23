from datetime import datetime, date
from collections import defaultdict

_reports: dict[date, list[dict]] = defaultdict(list)

def save_report(report: dict):
    today = date.today()
    report["saved_at"] = datetime.now().isoformat()
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
    total_cash = sum(r.get("cash", 0) for r in reports)
    total_card = sum(r.get("card", 0) for r in reports)
    opened     = any(r.get("type") == "opening" for r in reports)
    closed     = any(r.get("type") == "closing" for r in reports)
    return {
        "total_cash":     total_cash,
        "total_card":     total_card,
        "total":          total_cash + total_card,
        "opened":         opened,
        "closed":         closed,
        "reports_count":  len(reports),
    }
