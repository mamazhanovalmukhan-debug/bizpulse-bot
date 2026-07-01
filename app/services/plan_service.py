"""Тарифная система BizPulse — планы, лимиты, смена тарифа."""
from typing import Optional
from database.session import get_pool
from utils.formatting import fmt_money

# ─── Константы тарифов ───────────────────────────────────────────────────────

PLANS = {
    "START": {
        "code":          "START",
        "name":          "Старт",
        "max_locations": 1,
        "price":         199000,
        "description":   "1 точка · 1 990 ₽/мес",
    },
    "GROW": {
        "code":          "GROW",
        "name":          "Рост",
        "max_locations": 5,
        "price":         349000,
        "description":   "до 5 точек · 3 490 ₽/мес",
    },
    "NETWORK": {
        "code":          "NETWORK",
        "name":          "Сеть",
        "max_locations": 15,
        "price":         599000,
        "description":   "до 15 точек · 5 990 ₽/мес",
    },
    "ENTERPRISE": {
        "code":          "ENTERPRISE",
        "name":          "Enterprise",
        "max_locations": None,          # без лимита
        "price":         0,
        "description":   "16+ точек · индивидуально",
    },
}

PLAN_ORDER = ["START", "GROW", "NETWORK", "ENTERPRISE"]


# ─── Запросы к БД ────────────────────────────────────────────────────────────

async def get_plan(code: str) -> Optional[dict]:
    """Вернуть тариф из БД или из словаря PLANS."""
    row = await get_pool().fetchrow(
        "SELECT * FROM subscription_plans WHERE code=$1 AND is_active=TRUE", code
    )
    return dict(row) if row else None

async def get_all_plans() -> list:
    rows = await get_pool().fetch(
        "SELECT * FROM subscription_plans WHERE is_active=TRUE ORDER BY price_amount"
    )
    return [dict(r) for r in rows]

async def get_business_plan(business_id: int) -> dict:
    """Текущий тариф бизнеса. Если нет — возвращает START."""
    sub = await get_pool().fetchrow(
        "SELECT plan_code FROM subscriptions WHERE business_id=$1", business_id
    )
    code = sub["plan_code"] if sub and sub["plan_code"] else "START"
    return PLANS.get(code, PLANS["START"])

async def set_business_plan(business_id: int, plan_code: str):
    """Записать новый тариф в подписку."""
    plan_id_row = await get_pool().fetchrow(
        "SELECT id FROM subscription_plans WHERE code=$1", plan_code
    )
    plan_id = plan_id_row["id"] if plan_id_row else None
    await get_pool().execute(
        """UPDATE subscriptions
           SET plan_code=$2, plan_id=$3
           WHERE business_id=$1""",
        business_id, plan_code, plan_id
    )


# ─── Проверка лимитов ────────────────────────────────────────────────────────

async def check_location_limit(business_id: int) -> dict:
    """
    Проверить, можно ли добавить новую точку.
    Возвращает {ok, current, limit, plan_code, next_plan}
    """
    plan = await get_business_plan(business_id)
    current = await get_pool().fetchval(
        "SELECT COUNT(*) FROM locations WHERE business_id=$1 AND is_active=TRUE",
        business_id
    )
    current = int(current or 0)
    max_loc = plan.get("max_locations")

    if max_loc is None:   # ENTERPRISE — без лимита
        return {"ok": True, "current": current, "limit": None,
                "plan_code": plan["code"], "next_plan": None}

    if current < max_loc:
        return {"ok": True, "current": current, "limit": max_loc,
                "plan_code": plan["code"], "next_plan": None}

    # Найти следующий тариф
    idx = PLAN_ORDER.index(plan["code"]) if plan["code"] in PLAN_ORDER else 0
    next_code = PLAN_ORDER[idx + 1] if idx + 1 < len(PLAN_ORDER) else "ENTERPRISE"
    next_plan = PLANS.get(next_code)
    return {
        "ok":        False,
        "current":   current,
        "limit":     max_loc,
        "plan_code": plan["code"],
        "next_plan": next_plan,
    }

def location_limit_message(check: dict) -> str:
    """Текст ошибки при превышении лимита точек."""
    plan_name = PLANS.get(check["plan_code"], {}).get("name", check["plan_code"])
    next_p    = check.get("next_plan")
    if next_p:
        return (
            f"На тарифе «{plan_name}» доступно до {check['limit']} "
            f"{'точки' if check['limit'] == 1 else 'точек'}.\n\n"
            f"Для добавления новой точки перейдите на тариф "
            f"«{next_p['name']}» ({next_p['description']}).\n\n"
            f"Нажмите «Сменить тариф» или /change_plan"
        )
    return (
        f"На тарифе «{plan_name}» достигнут лимит точек ({check['limit']}).\n"
        f"Для расширения обратитесь в поддержку: /support"
    )


# ─── Форматирование ───────────────────────────────────────────────────────────

def plan_list_text() -> str:
    lines = ["💳 ТАРИФЫ BizPulse\n"]
    for code in PLAN_ORDER:
        p = PLANS[code]
        if code == "ENTERPRISE":
            lines.append(
                f"🔹 {p['name']} — 16+ точек\n"
                f"   Цена: индивидуально · /support"
            )
        else:
            loc_word = "точка" if p["max_locations"] == 1 else "точки"
            lines.append(
                f"🔹 {p['name']} — до {p['max_locations']} {loc_word}\n"
                f"   {fmt_money(p['price'])} / мес"
            )
    return "\n\n".join(lines)

def plan_summary_text(plan_code: str, sub, locations_count: int) -> str:
    """Текст для раздела «Тариф и оплата»."""
    plan = PLANS.get(plan_code, PLANS["START"])
    if not sub:
        return "Подписка не найдена."
    from services.subscription_service import subscription_status_text
    status = subscription_status_text(sub)
    max_loc = plan["max_locations"]
    loc_line = (
        f"Точек: {locations_count} / {max_loc}"
        if max_loc else f"Точек: {locations_count} (без лимита)"
    )
    price_line = (
        f"{fmt_money(plan['price'])}/мес"
        if plan["price"] else "Индивидуально"
    )
    return (
        f"💳 ТАРИФ И ОПЛАТА\n\n"
        f"Тариф: {plan['name']}\n"
        f"Цена: {price_line}\n"
        f"{loc_line}\n"
        f"Статус: {status}\n\n"
        f"Сменить тариф: /change_plan\n"
        f"Оплатить: /pay\n"
        f"Поддержка: /support"
    )
