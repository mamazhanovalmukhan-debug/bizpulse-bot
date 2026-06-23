import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ─── Настройки ────────────────────────────────────────────────────────────────

# Вставь свой Telegram ID (узнай у @userinfobot)
OWNER_ID = 18888758324:AAEqBGlXwraOMtdTmBupiVsEbetSFwBOCp4

# Сотрудники: { telegram_user_id: "Название точки" }
# Для теста вставь сюда свой ID
EMPLOYEE_POINTS = {
    8888758324:AAEqBGlXwraOMtdTmBupiVsEbetSFwBOCp4: "Тестовая точка",
}

# ─── Состояния FSM ────────────────────────────────────────────────────────────

class ClosingReport(StatesGroup):
    cash        = State()
    card        = State()
    expenses    = State()
    stock_notes = State()
    incidents   = State()

# ─── Клавиатуры ───────────────────────────────────────────────────────────────

def kb_skip():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def kb_no():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Нет")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

# ─── Хелперы ──────────────────────────────────────────────────────────────────

def parse_amount(text: str):
    cleaned = text.replace(" ", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None

def fmt(amount: float) -> str:
    return f"{amount:,.0f} ₽".replace(",", " ")

def build_report(data: dict, name: str, point: str) -> str:
    now   = datetime.now().strftime("%d.%m.%Y, %H:%M")
    cash  = data.get("cash", 0.0)
    card  = data.get("card", 0.0)
    total = cash + card

    expenses  = data.get("expenses", "").strip()
    stock     = data.get("stock_notes", "").strip()
    incidents = data.get("incidents", "").strip()

    exp_line = expenses  if expenses  and expenses  != "Пропустить" else "Нет"
    stk_line = stock     if stock     and stock     != "Пропустить" else "Без замечаний"
    inc_line = incidents if incidents and incidents not in ("Нет", "Пропустить") else "Нет"

    return (
        f"📋 *Закрытие смены*\n"
        f"📍 {point}\n"
        f"🕐 {now}\n"
        f"👤 {name}\n"
        f"{'─' * 28}\n\n"
        f"💰 *Выручка*\n"
        f"  Наличные:  `{fmt(cash)}`\n"
        f"  Безнал:    `{fmt(card)}`\n"
        f"  *Итого:    `{fmt(total)}`*\n\n"
        f"💸 *Расходы*\n"
        f"  {exp_line}\n\n"
        f"📦 *Остатки*\n"
        f"  {stk_line}\n\n"
        f"⚠️ *Происшествия*\n"
        f"  {inc_line}"
    )

# ─── Роутер ───────────────────────────────────────────────────────────────────

router = Router()

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

# Старт
@router.message(F.text == "/закрытие", is_employee)
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ClosingReport.cash)
    await message.answer(
        "📋 *Отчёт по закрытию смены*\n\nОтвечай на вопросы по одному.\n\n"
        "💵 Сколько наличных в кассе?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

# Шаг 1 — наличные
@router.message(ClosingReport.cash)
async def step_cash(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Введи сумму числом, например: `12400`", parse_mode="Markdown")
        return
    await state.update_data(cash=amount)
    await state.set_state(ClosingReport.card)
    await message.answer(
        f"✅ Наличные: *{fmt(amount)}*\n\n💳 Сколько по безналу / терминалу?",
        parse_mode="Markdown",
    )

# Шаг 2 — безнал
@router.message(ClosingReport.card)
async def step_card(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Введи сумму числом, например: `8750`", parse_mode="Markdown")
        return
    data = await state.get_data()
    total = data["cash"] + amount
    await state.update_data(card=amount)
    await state.set_state(ClosingReport.expenses)
    await message.answer(
        f"✅ Безнал: *{fmt(amount)}*\n"
        f"Итого выручка: *{fmt(total)}*\n\n"
        "💸 Были расходы? Напиши сумму и на что:\n"
        "`1200 — скотч и пакеты`\n\n"
        "Если нет — нажми *Пропустить*.",
        parse_mode="Markdown",
        reply_markup=kb_skip(),
    )

# Шаг 3 — расходы
@router.message(ClosingReport.expenses)
async def step_expenses(message: Message, state: FSMContext):
    await state.update_data(expenses=message.text)
    await state.set_state(ClosingReport.stock_notes)
    await message.answer(
        "✅ Записал.\n\n"
        "📦 Что заканчивается или нужно заказать?\n"
        "Например: `молоко, хлеб`\n\n"
        "Если всё в порядке — нажми *Пропустить*.",
        parse_mode="Markdown",
        reply_markup=kb_skip(),
    )

# Шаг 4 — остатки
@router.message(ClosingReport.stock_notes)
async def step_stock(message: Message, state: FSMContext):
    await state.update_data(stock_notes=message.text)
    await state.set_state(ClosingReport.incidents)
    await message.answer(
        "✅ Записал.\n\n"
        "⚠️ Были происшествия или важные события?\n"
        "Например: `сломался холодильник`\n\n"
        "Если всё спокойно — нажми *Нет*.",
        parse_mode="Markdown",
        reply_markup=kb_no(),
    )

# Шаг 5 — происшествия → финал
@router.message(ClosingReport.incidents)
async def step_incidents(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(incidents=message.text)
    data  = await state.get_data()
    await state.clear()

    user   = message.from_user
    point  = EMPLOYEE_POINTS.get(user.id, "Неизвестная точка")
    report = build_report(data, user.full_name, point)

    await message.answer(
        "✅ *Отчёт отправлен!* Хорошей ночи 🌙\n\n" + report,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    try:
        await bot.send_message(chat_id=OWNER_ID, text=report, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка отправки владельцу: {e}")

# Чужие — отказ
@router.message(F.text == "/закрытие")
async def cmd_denied(message: Message):
    await message.answer("У вас нет доступа к этой команде.")
