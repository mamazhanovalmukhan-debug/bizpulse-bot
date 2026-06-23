from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from config import EMPLOYEE_POINTS, OWNER_ID

router = Router()

class InterimState(StatesGroup):
    waiting_cash = State()
    waiting_card = State()

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

def employee_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌅 Открытие смены")],
            [KeyboardButton(text="🌙 Закрытие смены")],
            [KeyboardButton(text="📊 Промежуточная выручка")],
            [KeyboardButton(text="💡 Предложение")],
        ],
        resize_keyboard=True,
    )

def fmt(amount):
    return f"{amount:,.0f} р".replace(",", " ")

def parse_amount(text):
    try:
        return float(text.replace(" ", "").replace(",", ".").strip())
    except ValueError:
        return None

@router.message(Command("start"), is_employee)
async def employee_start(message: Message):
    name  = message.from_user.first_name
    point = EMPLOYEE_POINTS.get(message.from_user.id, "")
    await message.answer(
        f"Привет, {name}!\n\nТочка: {point}\n\nВыбери действие:",
        reply_markup=employee_keyboard(),
    )

# ─── Промежуточная выручка ────────────────────────────────────────────────────

@router.message(F.text == "📊 Промежуточная выручка", is_employee)
async def interim_start(message: Message, state: FSMContext):
    await state.set_state(InterimState.waiting_cash)
    await message.answer(
        "Промежуточная выручка\n\n"
        "Сколько сейчас наличных в кассе?\n"
        "Например: 8500"
    )

@router.message(InterimState.waiting_cash)
async def interim_cash(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Введи сумму числом, например: 8500")
        return
    await state.update_data(cash=amount)
    await state.set_state(InterimState.waiting_card)
    await message.answer(
        f"Наличные: {fmt(amount)}\n\n"
        "Сколько прошло по безналу с начала смены?\n"
        "Если не знаешь — напиши 0"
    )

@router.message(InterimState.waiting_card)
async def interim_card(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Введи сумму числом, например: 3200")
        return

    data  = await state.get_data()
    await state.clear()

    cash  = data.get("cash", 0)
    card  = amount
    total = cash + card
    now   = datetime.now().strftime("%d.%m.%Y, %H:%M")
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")

    text = (
        f"Промежуточная выручка\n"
        f"Точка: {point}\n"
        f"Время: {now}\n"
        f"Сотрудник: {user.full_name}\n"
        f"────────────────────\n"
        f"Наличные:  {fmt(cash)}\n"
        f"Безнал:    {fmt(card)}\n"
        f"Итого:     {fmt(total)}"
    )

    await message.answer(f"Отправил владельцу!\n\n{text}")

    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        import logging
        logging.error(f"Ошибка отправки промежуточной: {e}")

# ─── Предложение от сотрудника ────────────────────────────────────────────────

@router.message(F.text == "💡 Предложение", is_employee)
async def suggestion_start(message: Message, state: FSMContext):
    await state.set_state(SuggestionState.waiting_text)
    await message.answer(
        "Напиши своё предложение.\n\n"
        "Это может быть:\n"
        "- Идея нового напитка или блюда\n"
        "- Предложение заказать новый товар\n"
        "- Любое улучшение для точки\n\n"
        "Пиши в свободной форме:"
    )

class SuggestionState(StatesGroup):
    waiting_text = State()

@router.message(SuggestionState.waiting_text)
async def suggestion_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")
    now   = datetime.now().strftime("%d.%m.%Y, %H:%M")

    text = (
        f"Предложение от сотрудника\n"
        f"Точка: {point}\n"
        f"От: {user.full_name}\n"
        f"Время: {now}\n"
        f"────────────────────\n"
        f"{message.text}"
    )

    await message.answer("Предложение отправлено владельцу! Спасибо за инициативу 👍")

    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        import logging
        logging.error(f"Ошибка отправки предложения: {e}")
