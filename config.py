import os
from datetime import timezone, timedelta

BOT_TOKEN  = os.getenv("BOT_TOKEN")
OWNER_ID   = int(os.getenv("OWNER_ID", "0"))
GROQ_KEY   = os.getenv("GROQ_API_KEY", "")

# Московский часовой пояс
MSK = timezone(timedelta(hours=3))

# Москва UTC+3: 10:00=07UTC, 22:00=19UTC, 23:30=20UTC
OPENING_HOUR_UTC = int(os.getenv("OPENING_HOUR_UTC", "7"))
CLOSING_HOUR_UTC = int(os.getenv("CLOSING_HOUR_UTC", "19"))
DIGEST_HOUR_UTC  = int(os.getenv("DIGEST_HOUR_UTC",  "20"))

COMPETITORS = [
    {"name": "Bosco Café",    "address": "Красная пл., 3 (ГУМ)", "avg_check": 2500, "rating": 3.7},
    {"name": "Шоколадница",   "address": "Охотный ряд",           "avg_check": 600,  "rating": 4.1},
    {"name": "Stars Coffee",  "address": "ГУМ, Красная пл.",      "avg_check": 650,  "rating": 4.0},
    {"name": "Му-Му",         "address": "Охотный ряд, 2",        "avg_check": 500,  "rating": 4.2},
    {"name": "Surf Coffee",   "address": "Центр Москвы",          "avg_check": 400,  "rating": 4.5},
    {"name": "Кофемания",     "address": "Центр Москвы",          "avg_check": 800,  "rating": 4.6},
]

def load_employees() -> dict:
    raw = os.getenv("EMPLOYEES", "")
    result = {}
    if not raw:
        return result
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        user_id, point = entry.split(":", 1)
        try:
            result[int(user_id.strip())] = point.strip()
        except ValueError:
            continue
    return result

EMPLOYEE_POINTS = load_employees()

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан.")
if not OWNER_ID:
    raise ValueError("OWNER_ID не задан.")
