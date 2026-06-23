import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import OWNER_ID, EMPLOYEE_POINTS
from storage import save_report

router = Router()

class ClosingReport(StatesGroup):
    cash        = State()
    card        = State()
    expenses    = State()
    stock_notes = State()
    incidents   = State()

def kb_skip():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True, one_time_keyboard=True,
    )

def kb_no():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Нет")]],
        resize_keyboard=True, one_time_keyboard=True,
    )

def parse_amount(text):
    try:
        return float(text.replace(" ", "").replace(",", ".").strip())
    except ValueError:
        return None

def fmt(amount):
    return f"{amount:,.0f} ₽".replace(",", " ")

def build_report(data, name, point):
    now   = datetime.now().strftime("%d.%m.%Y, %H:%M")
    cash  = data.get("cash", 0.0)
    card  = data.get("card", 0.0)
    total = cash + card
    exp   = data.get("expenses", "").strip()
    stock = data.get("stock_notes", "").strip()
    inc   = data.get("incidents", "").strip()
    return (
        f"📋 *Закрытие смены*\n📍 {point}\n🕐 {now}\n👤 {name}\n"
        f"{'─' * 28}\n\n"
        f"💰 *Выручка*\n"
        f"  Наличные:  `{fmt(cash)}`\n"
        f"  Безнал:    `{fmt(card)}`\n"
        f"  *Итого:    `{fmt(total)}`*\n\n"
        f"💸 *Расходы*\n  {exp if exp and exp != 'Пропустить' else 'Нет'}\n\n"
        f"📦 *Остатки*\n  {stock if stock and stock != 'Пропустить' else 'Без замечаний'}\n\n"
        f"⚠️ *Происшествия*\n  {inc if inc and inc not in ('Нет', 'Пропустить') else 'Нет'}"
    )

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

@router.message(F.text.in_(["/закрытие", "🌙 Закрытие смены"]), is_employee)
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ClosingReport.cash)
    await message.answer(
        "📋 *Закрытие смены*\n\n💵 Сколько наличных в кассе?",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove(),
    )

@router.message(ClosingReport.cash)
async def step_cash(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Введи сумму числом, например: `12400`", parse_mode="Markdown")
        return
    await state.update_data(cash=amount)
    await state.set_state(ClosingReport.card)
    await message.answer(
        f"✅ Наличные: *{fmt(amount)}*\n\n💳 Сколько по безналу?",
        parse_mode="Markdown",
    )

@router.message(ClosingReport.card)
async def step_card(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Введи сумму числом, например: `8750`", parse_mode="Markdown")
        return
    data  = await state.get_data()
    total = data["cash"] + amount
    await state.update_data(card=amount)
    await state.set_state(ClosingReport.expenses)
    await message.answer(
        f"✅ Безнал: *{fmt(amount)}*\nИтого: *{fmt(total)}*\n\n"
        "💸 Были расходы? Напиши сумму и на что:\n`1200 — стаканы`\n\n"
        "Если нет — *Пропустить*.",
        parse_mode="Markdown", reply_markup=kb_skip(),
    )

@router.message(ClosingReport.expenses)
async def step_expenses(message: Message, state: FSMContext):
    await state.update_data(expenses=message.text)
    await state.set_state(ClosingReport.stock_notes)
    await message.answer(
        "✅ Записал.\n\n📦 Что заканчивается или нужно заказать?\n"
        "Например: `молоко, стаканы`\n\nЕсли всё ок — *Пропустить*.",
        parse_mode="Markdown", reply_markup=kb_skip(),
    )

@router.message(ClosingReport.stock_notes)
async def step_stock(message: Message, state: FSMContext):
    await state.update_data(stock_notes=message.text)
    await state.set_state(ClosingReport.incidents)
    await message.answer(
        "✅ Записал.\n\n⚠️ Были происшествия?\n"
        "Например: `сломался кофемат`\n\nЕсли нет — *Нет*.",
        parse_mode="Markdown", reply_markup=kb_no(),
    )

@router.message(ClosingReport.incidents)
async def step_incidents(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(incidents=message.text)
    data  = await state.get_data()
    await state.clear()
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "Неизвестная точка")
    text  = build_report(data, user.full_name, point)
    save_report({
        "type": "closing", "point": point,
        "employee": user.full_name,
        "cash": data.get("cash", 0),
        "card": data.get("card", 0),
        "expenses": data.get("expenses", ""),
        "stock_notes": data.get("stock_notes", ""),
        "incidents": data.get("incidents", ""),
    })
    await message.answer(
        "✅ *Отчёт отправлен!* Хорошей ночи 🌙\n\n" + text,
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка: {e}")

@router.message(F.text.in_(["/закрытие", "🌙 Закрытие смены"]))
async def cmd_denied(message: Message):
    await message.answer("У вас нет доступа к этой команде.")
