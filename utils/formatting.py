"""Форматирование чисел, сумм, категорий."""
from datetime import datetime
from zoneinfo import ZoneInfo

def fmt_money(amount) -> str:
    try:
        return f"{int(float(amount or 0)):,}".replace(",", " ") + " ₽"
    except Exception:
        return "0 ₽"

def fmt_dt(dt: datetime, tz: str = "Europe/Moscow") -> str:
    if dt is None:
        return "—"
    try:
        local = dt.astimezone(ZoneInfo(tz))
        return local.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(dt)

def parse_money(text: str):
    """Парсит строку в float. Возвращает None если не число."""
    if not text:
        return None
    cleaned = text.replace(" ", "").replace(",", ".").strip()
    try:
        val = float(cleaned)
        return val if val >= 0 else None
    except ValueError:
        return None

CATEGORY_NAMES = {
    "coffee_shop": "Кофейня",
    "shawarma":    "Шаурма",
    "tobacco":     "Табачный магазин",
    "bakery":      "Пекарня",
    "retail":      "Магазин",
    "other":       "Другое",
}

ROLE_NAMES = {
    "owner":    "Владелец",
    "manager":  "Менеджер",
    "employee": "Сотрудник",
    "admin":    "Администратор",
}

SEVERITY_EMOJI = {
    "info":     "ℹ️",
    "warning":  "⚠️",
    "critical": "🚨",
}
