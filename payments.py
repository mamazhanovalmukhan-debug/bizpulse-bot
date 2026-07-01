"""Команды владельца v3 — без конкурентов, с аналитикой сотрудников."""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import (
    get_business_by_owner, get_locations, get_business_users,
    get_today_shifts, get_week_shifts, get_business_movements,
    get_subscription, get_open_stock_alerts, get_all_stock_notes,
    get_low_stock_products, count_employees, add_business_user
)
from services.ai_service import analyze_day, analyze_week, analyze_stock
from services.invite_service import generate_invite
from services.analytics_service import (
    compare_employees, get_employee_stats, get_daily_summary
)
from keyboards.owner import (
    owner_main_kb, kb_cancel, kb_skip_cancel,
    roles_kb, locations_kb
)
from utils.formatting import fmt_money, ROLE_NAMES
from config import config

router = Router()

class InviteState(StatesGroup):
    location = State()
    role     = State()

async def get_biz(tg_id: int):
    return await get_business_by_owner(tg_id)


# ── СТАТУС ──────────────────────────────────────────────────────────────────

@router.message(F.text == "📍 Статус сейчас")
@router.message(Command("status"))
async def status_now(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    shifts   = await get_today_shifts(biz["id"])
    locs     = await get_locations(biz["id"])
    opened   = {s["location_name"] for s in shifts if s["status"] == "open"}
    closed   = {s["location_name"] for s in shifts if s["status"] == "closed"}
    movs     = await get_business_movements(biz["id"], days=1)
    cash_r   = sum(m["amount"] for m in movs if m["type"] == "sale_cash")
    card_r   = sum(m["amount"] for m in movs if m["type"] == "sale_card")
    agg_r    = sum(m["amount"] for m in movs if m["type"] == "sale_sbp")
    alerts   = await get_open_stock_alerts(biz["id"])
    sub      = await get_subscription(biz["id"])
    loc_lines = []
    for l in locs:
        o = "✅" if l["name"] in opened else "❌"
        c = "✅" if l["name"] in closed else "🔄"
        loc_lines.append(f"{l['name']}: открытие {o} · закрытие {c}")
    alert_line = f"\n⚠️ Складских алертов: {len(alerts)}" if alerts else ""
    await message.answer(
        f"📍 СТАТУС: {biz['name']}\n{'─'*25}\n"
        + ("\n".join(loc_lines) or "Нет точек") + "\n\n"
        f"Выручка сегодня:\n"
        f"Нал: {fmt_money(cash_r)} · Безнал: {fmt_money(card_r)} · Агрег: {fmt_money(agg_r)}\n"
        f"Итого: {fmt_money(cash_r + card_r + agg_r)}"
        + alert_line + f"\n\nПодписка: {subscription_status_text(sub)}"
    )


# ── ИТОГИ ДНЯ ────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Итоги дня")
@router.message(Command("today"))
async def today_results(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    text = await get_daily_summary(biz["id"], biz["name"])
    await message.answer(text)


# ── ИТОГИ НЕДЕЛИ ────────────────────────────────────────────────────────────

@router.message(F.text == "📈 Итоги недели")
@router.message(Command("week"))
async def week_results(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    movs = await get_business_movements(biz["id"], days=7)
    if not movs:
        await message.answer("За прошедшие 7 дней данных нет.")
        return
    total = sum(m["amount"] for m in movs if m["type"].startswith("sale_"))
    await message.answer(f"Выручка за 7 дней: {fmt_money(total)}\n\nЗапрашиваю ИИ-анализ...")
    from database.models import get_today_reports, get_week_reports
    reports = await get_week_reports(biz["id"])
    result  = await analyze_week(biz["id"], biz["name"],
                                  [dict(r) for r in reports],
                                  [dict(m) for m in movs])
    await message.answer(f"📈 ИТОГИ НЕДЕЛИ\n\n{result}")


# ── ИИ-АНАЛИЗ ───────────────────────────────────────────────────────────────

@router.message(F.text == "🤖 ИИ-анализ")
async def ai_analysis(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    shifts    = await get_today_shifts(biz["id"])
    movs      = await get_business_movements(biz["id"], days=1)
    notes     = await get_all_stock_notes(biz["id"])
    low_stock = await get_low_stock_products(biz["id"])
    if not shifts and not movs:
        await message.answer("Нет данных за сегодня.")
        return
    await message.answer("🤖 Анализирую данные дня...")
    from database.models import get_today_reports
    reports = await get_today_reports(biz["id"])
    result  = await analyze_day(
        biz["id"], biz["name"], biz["category"],
        [dict(r) for r in reports], [dict(m) for m in movs],
        notes, [dict(p) for p in low_stock]
    )
    await message.answer(f"🤖 ИИ-АНАЛИЗ ДНЯ\n\n{result}")


# ── КАССА ────────────────────────────────────────────────────────────────────

@router.message(F.text == "🧾 Касса")
async def cash_overview(message: Message):
    biz  = await get_biz(message.from_user.id)
    if not biz:
        return
    movs = await get_business_movements(biz["id"], days=1)
    locs = {l["id"]: l["name"] for l in await get_locations(biz["id"])}
    by_loc: dict = {}
    for m in movs:
        lid = m["location_id"]
        if lid not in by_loc:
            by_loc[lid] = {"cash": 0, "card": 0, "agg": 0,
                           "exp": 0, "name": locs.get(lid, "?")}
        t = m["type"]
        if t == "sale_cash":  by_loc[lid]["cash"] += float(m["amount"])
        if t == "sale_card":  by_loc[lid]["card"] += float(m["amount"])
        if t == "sale_sbp":   by_loc[lid]["agg"]  += float(m["amount"])
        if t == "expense":    by_loc[lid]["exp"]  += float(m["amount"])
    if not by_loc:
        await message.answer("За сегодня операций нет.")
        return
    lines = []
    for v in by_loc.values():
        total = v["cash"] + v["card"] + v["agg"]
        lines.append(
            f"📍 {v['name']}\n"
            f"  Нал: {fmt_money(v['cash'])} · Безнал: {fmt_money(v['card'])}"
            f" · Агрег: {fmt_money(v['agg'])}\n"
            f"  Итого: {fmt_money(total)} · Расходы: {fmt_money(v['exp'])}"
        )
    await message.answer("🧾 КАССА ЗА СЕГОДНЯ\n\n" + "\n\n".join(lines))


# ── ТОЧКИ ────────────────────────────────────────────────────────────────────

@router.message(F.text == "🏪 Точки")
@router.message(Command("locations"))
async def list_locations(message: Message):
    biz  = await get_biz(message.from_user.id)
    if not biz:
        return
    locs = await get_locations(biz["id"])
    if not locs:
        await message.answer("Точек нет.")
        return
    lines = [
        f"{i+1}. {l['name']}\n"
        f"   {l.get('address') or 'адрес не указан'}\n"
        f"   {l['open_time']}:00–{l['close_time']}:00"
        for i, l in enumerate(locs)
    ]
    await message.answer(f"🏪 ТОЧКИ ({len(locs)})\n\n" + "\n\n".join(lines))


# ── СОТРУДНИКИ ───────────────────────────────────────────────────────────────

@router.message(F.text == "👥 Сотрудники")
@router.message(Command("employees"))
async def list_employees(message: Message):
    biz  = await get_biz(message.from_user.id)
    if not biz:
        return
    users = await get_business_users(biz["id"])
    if not users:
        await message.answer(
            "Сотрудников нет.\n\nПригласите: /invite_employee"
        )
        return
    lines = []
    for u in users:
        role = ROLE_NAMES.get(u["role"], u["role"])
        loc  = u.get("location_name") or "точка не назначена"
        lines.append(f"• {u['full_name']} [{role}] — {loc}")
    cnt = await count_employees(biz["id"])
    await message.answer(
        f"👥 СОТРУДНИКИ ({cnt}/{config.PLAN_EMPLOYEES_LIMIT})\n\n"
        + "\n".join(lines) + "\n\n"
        + "Добавить: /invite_employee\n"
        + "Аналитика: /employee_stats"
    )

@router.message(Command("employee_stats"))
async def employee_stats_cmd(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    result = await compare_employees(biz["id"])
    await message.answer(f"👥 АНАЛИТИКА СОТРУДНИКОВ\n\n{result}")

@router.message(Command("invite_employee"))
async def invite_start(message: Message, state: FSMContext):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    cnt = await count_employees(biz["id"])
    if cnt >= config.PLAN_EMPLOYEES_LIMIT:
        await message.answer(
            f"Достигнут лимит: {config.PLAN_EMPLOYEES_LIMIT} сотрудников."
        )
        return
    locs = await get_locations(biz["id"])
    if not locs:
        await message.answer("Нет активных точек.")
        return
    await state.set_state(InviteState.location)
    await message.answer(
        "Приглашение сотрудника\n\nНа какую точку?",
        reply_markup=locations_kb(locs)
    )

@router.message(InviteState.location)
async def invite_location(message: Message, state: FSMContext):
    biz  = await get_biz(message.from_user.id)
    locs = await get_locations(biz["id"])
    loc  = next((l for l in locs if l["name"] == message.text), None)
    if not loc:
        await message.answer("Выберите точку из списка:")
        return
    await state.update_data(location_id=loc["id"], location_name=loc["name"])
    await state.set_state(InviteState.role)
    await message.answer("Роль сотрудника?", reply_markup=roles_kb())

@router.message(InviteState.role, F.text.in_(["Сотрудник", "Менеджер"]))
async def invite_role(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    role  = "employee" if message.text == "Сотрудник" else "manager"
    biz   = await get_biz(message.from_user.id)
    link  = await generate_invite(
        biz["id"], data["location_id"], role, config.BOT_USERNAME
    )
    role_text = "сотрудника" if role == "employee" else "менеджера"
    await message.answer(
        f"✅ Ссылка для {role_text}:\n\n{link}\n\n"
        f"Точка: {data['location_name']}\n"
        f"Действует 7 дней · Одноразовая",
        reply_markup=owner_main_kb()
    )


# ── ПОДПИСКА ─────────────────────────────────────────────────────────────────

# /pay и /subscription обрабатываются в handlers/billing.py


# ── СКЛАД (обзор) ─────────────────────────────────────────────────────────────

@router.message(F.text == "📦 Склад")
async def warehouse_overview(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    alerts    = await get_open_stock_alerts(biz["id"])
    low_stock = await get_low_stock_products(biz["id"])
    lines     = ["📦 СКЛАД"]
    if low_stock:
        lines.append(f"\n⚠️ Ниже минимума ({len(low_stock)}):")
        for p in low_stock[:5]:
            lines.append(
                f"• {p['name']}: {p['current_stock']} {p['unit']} "
                f"(мин. {p['min_stock']})"
            )
    if alerts:
        lines.append(f"\n🚨 Открытых алертов: {len(alerts)}")
    if not low_stock and not alerts:
        lines.append("\n✅ Всё в порядке")
    lines.append(
        "\n\nПоставки: /deliveries\n"
        "Инвентаризация: /inventory\n"
        "Товары: /products"
    )
    await message.answer("\n".join(lines))


# ── HELP ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 СПРАВКА BizPulse\n\n"
        "/status — статус бизнеса\n"
        "/today — итоги дня\n"
        "/week — итоги недели\n"
        "/locations — точки\n"
        "/employees — сотрудники\n"
        "/employee_stats — аналитика сотрудников\n"
        "/invite_employee — пригласить сотрудника\n"
        "/subscription — статус подписки\n"
        "/pay — оплатить\n"
        "/support — поддержка\n"
        "/legal — документы\n"
        "/deliveries — поставки\n"
        "/inventory — инвентаризация\n"
        "/products — товары"
    )


# ── Добавить точку (с проверкой лимита тарифа) ───────────────────────────────

@router.message(Command("add_location"))
async def add_location_check(message: Message):
    """Проверяет лимит тарифа перед добавлением точки."""
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    from services.plan_service import check_location_limit, location_limit_message
    check = await check_location_limit(biz["id"])
    if not check["ok"]:
        await message.answer(location_limit_message(check))
    else:
        await message.answer(
            f"Текущих точек: {check['current']}"
            + (f" из {check['limit']}" if check["limit"] else "") + "\n\n"
            "Добавление новых точек через онбординг (/start) или обратитесь в /support."
        )


# ── BUSINESS ADVISOR ──────────────────────────────────────────────────────────

@router.message(F.text == "🧠 Советник")
@router.message(Command("advisor"))
async def advisor_cmd(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    await message.answer("🧠 Формирую рекомендации...")
    from services.advisor_service import generate_daily_advice
    advice = await generate_daily_advice(biz["id"], biz["name"], biz["category"])
    await message.answer(advice)


# ── HEALTH SCORE ──────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Health Score")
@router.message(Command("health"))
async def health_score_cmd(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    from services.advisor_service import compute_health_score, format_health_score
    hs   = await compute_health_score(biz["id"])
    text = format_health_score(hs, biz["name"])
    await message.answer(text)


# ── АНОМАЛИИ ─────────────────────────────────────────────────────────────────

@router.message(Command("anomalies"))
async def anomalies_cmd(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    from database.models import get_open_anomalies
    from utils.formatting import SEVERITY_EMOJI
    anomalies = await get_open_anomalies(biz["id"])
    if not anomalies:
        await message.answer("✅ Открытых аномалий нет.")
        return
    lines = [f"Аномалий: {len(anomalies)}\n"]
    for a in anomalies[:10]:
        e = SEVERITY_EMOJI.get(a.get("severity","info"), "•")
        lines.append(f"{e} {a['title']}\n   {a.get('description','')}")
    await message.answer("\n\n".join(lines))


# ── AUDIT LOG ─────────────────────────────────────────────────────────────────

@router.message(Command("audit"))
async def audit_log_cmd(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    from services.audit_service import get_audit_log
    logs = await get_audit_log(biz["id"], limit=20)
    if not logs:
        await message.answer("Журнал действий пуст.")
        return
    lines = ["ЖУРНАЛ ДЕЙСТВИЙ (последние 20)\n"]
    for entry in logs:
        dt  = entry["created_at"].strftime("%d.%m %H:%M")
        who = entry.get("full_name") or str(entry.get("user_id","?"))
        lines.append(f"• {dt} · {who}\n  {entry['action']}")
    await message.answer("\n\n".join(lines))


# ── НАСТРОЙКИ (заглушка) ─────────────────────────────────────────────────────

@router.message(F.text == "⚙️ Настройки")
async def settings_stub(message: Message):
    biz = await get_biz(message.from_user.id)
    if not biz:
        return
    await message.answer(
        f"⚙️ Настройки бизнеса\n\n"
        f"Бизнес: {biz['name']}\n\n"
        f"Доступные команды:\n"
        f"• /subscription — тариф и оплата\n"
        f"• /locations — точки\n"
        f"• /employees — сотрудники\n"
        f"• /invite_employee — добавить сотрудника\n"
        f"• /support — поддержка"
    )
