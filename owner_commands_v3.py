from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from config import OWNER_ID, COMPETITORS
from storage import get_today_summary, get_today_reports, get_week_reports, get_all_stock_notes
from ai_analyst import analyze_day, analyze_competitors, weekly_advice, analyze_stock
from competitor_monitor import get_competitor_intelligence, get_raw_competitor_posts

router = Router()

def is_owner(message: Message) -> bool:
    return message.from_user.id == OWNER_ID

def fmt(amount):
    return f"{amount:,.0f} р".replace(",", " ")

def owner_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статус сейчас"),  KeyboardButton(text="📈 Итоги дня")],
            [KeyboardButton(text="🤖 ИИ-анализ дня"),  KeyboardButton(text="🔍 Разведка")],
            [KeyboardButton(text="📦 Анализ остатков"), KeyboardButton(text="📅 Итоги недели")],
        ],
        resize_keyboard=True,
    )

@router.message(Command("start"), is_owner)
async def owner_start(message: Message):
    await message.answer(
        "BizPulse — твой цифровой управляющий\n\nВыбери действие:",
        reply_markup=owner_keyboard(),
    )

@router.message(F.text == "📊 Статус сейчас", is_owner)
async def status_now(message: Message):
    s = get_today_summary()
    await message.answer(
        f"Статус прямо сейчас\n\n"
        f"Открытие: {'✅ заполнено' if s['opened'] else '❌ нет отчёта'}\n"
        f"Закрытие: {'✅ заполнено' if s['closed'] else '🔄 смена идёт'}\n\n"
        f"Выручка за день\n"
        f"Наличные: {fmt(s['total_cash'])}\n"
        f"Безнал: {fmt(s['total_card'])}\n"
        f"Итого: {fmt(s['total'])}\n\n"
        f"Отчётов сегодня: {s['reports_count']}",
    )

@router.message(F.text == "📈 Итоги дня", is_owner)
async def today_results(message: Message):
    reports = get_today_reports()
    if not reports:
        await message.answer("За сегодня отчётов ещё нет.")
        return
    lines = []
    for r in reports:
        t = "Открытие" if r.get("type") == "opening" else "Закрытие"
        revenue = r.get("cash", 0) + r.get("card", 0)
        line = f"{t} — {r.get('point', '?')}"
        if revenue:
            line += f" — {fmt(revenue)}"
        lines.append(line)
    await message.answer("Отчёты за сегодня\n\n" + "\n".join(lines))

@router.message(F.text == "🤖 ИИ-анализ дня", is_owner)
async def ai_day(message: Message):
    reports = get_today_reports()
    if not reports:
        await message.answer("Нет данных за сегодня.")
        return
    await message.answer("Анализирую...")
    result = await analyze_day(reports)
    await message.answer(f"ИИ-анализ дня\n\n{result}")

@router.message(F.text == "🔍 Разведка", is_owner)
async def competitor_intel(message: Message):
    await message.answer("Читаю посты Stars Coffee, Surf Coffee и Кофемании...")
    raw = await get_raw_competitor_posts()
    await message.answer(raw)
    await message.answer("Формирую совет на основе активности конкурентов...")
    advice = await get_competitor_intelligence()
    await message.answer(f"Совет на сегодня\n\n{advice}")

@router.message(F.text == "📦 Анализ остатков", is_owner)
async def stock(message: Message):
    notes = get_all_stock_notes()
    if not notes:
        await message.answer("Записей об остатках пока нет.")
        return
    await message.answer("Анализирую остатки...")
    result = await analyze_stock(notes)
    await message.answer(f"Анализ остатков\n\n{result}")

@router.message(F.text == "📅 Итоги недели", is_owner)
async def weekly(message: Message):
    reports = [r for r in get_week_reports() if r.get("type") == "closing"]
    if not reports:
        await message.answer("За эту неделю данных нет.")
        return
    total = sum(r.get("cash", 0) + r.get("card", 0) for r in reports)
    await message.answer(f"Выручка за неделю: {fmt(total)}\nЗапрашиваю анализ ИИ...")
    result = await weekly_advice(reports)
    await message.answer(f"Итоги недели\n\n{result}")
