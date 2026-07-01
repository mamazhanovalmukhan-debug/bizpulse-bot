"""Работа с датами и временными зонами."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def trial_ends_at(days: int = 30) -> datetime:
    return now_utc() + timedelta(days=days)

def subscription_end(days: int = 30) -> datetime:
    return now_utc() + timedelta(days=days)

def local_hour(tz_name: str, hour: int) -> datetime:
    """Ближайший moment когда в tz_name будет hour:00."""
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)

TIMEZONES = [
    ("Europe/Moscow",       "МСК (UTC+3)"),
    ("Europe/Samara",       "Самара (UTC+4)"),
    ("Asia/Yekaterinburg",  "Екатеринбург (UTC+5)"),
    ("Asia/Omsk",           "Омск (UTC+6)"),
    ("Asia/Krasnoyarsk",    "Красноярск (UTC+7)"),
    ("Asia/Irkutsk",        "Иркутск (UTC+8)"),
    ("Asia/Yakutsk",        "Якутск (UTC+9)"),
    ("Asia/Vladivostok",    "Владивосток (UTC+10)"),
]
