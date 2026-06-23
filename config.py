import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID  = int(os.getenv("OWNER_ID", "0"))

# Сотрудники задаются через переменную окружения в формате:
# EMPLOYEES=111111111:Точка №1,222222222:Точка №2
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
    raise ValueError("BOT_TOKEN не задан в переменных окружения.")
if not OWNER_ID:
    raise ValueError("OWNER_ID не задан в переменных окружения.")
