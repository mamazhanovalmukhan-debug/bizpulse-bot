import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import EMPLOYEE_POINTS, OWNER_ID, MSK
from storage import get_last_cash_balance, set_last_cash_balance

router = Router()

class InterimState(StatesGroup):
    waiting_cash = State()
    waiting_card = State()

class SuggestionState(StatesGroup):
    waiting_text = State()

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
    cleaned = text.replace(" ", "").replace(",", ".").strip()
    try:
        val = float(cleaned)
        if val < 0:
            return None
        return val
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
        "Сколько сейчас наличных в кассе (всего, включая утренний остаток)?\n"
        "Введи только цифры:",
        reply_markup=ReplyKeyboardRemove(),
    )

@router.message(InterimState.waiting_cash)
async def interim_cash(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 8500\nПопробуй ещё раз:")
        return

    opening_cash = get_last_cash_balance()
    diff = amount - opening_cash

    # Проверяем — наличных не может стать меньше чем было на открытии
    if amount < opening_cash:
        user  = message.from_user
        point = EMPLOYEE_POINTS.get(user.id, "?")
        alert = (
            f"Внимание! Наличных стало меньше!\n\n"
            f"Точка: {point}\n"
            f"Сотрудник: {user.full_name}\n"
            f"Время: {datetime.now(MSK).strftime('%H:%M')} МСК\n\n"
            f"На открытии было: {fmt(opening_cash)}\n"
            f"Сейчас: {fmt(amount)}\n"
            f"Не хватает: {fmt(opening_cash - amount)}"
        )
        await message.answer(
            f"Внимание! Наличных меньше чем было на открытии.\n\n"
            f"На открытии: {fmt(opening_cash)}\n"
            f"Сейчас: {fmt(amount)}\n\n"
            "Владелец уведомлён."
        )
        try:
            await bot.send_message(chat_id=OWNER_ID, text=alert)
        except Exception as e:
            logging.error(f"Ошибка алерта: {e}")

    await state.update_data(cash=amount)
    await state.set_state(InterimState.waiting_card)
    await message.answer(
        f"Наличные: {fmt(amount)}\n\n"
        "Сколько прошло по безналу с начала смены?\n"
        "Если не знаешь — напиши 0:"
    )

@router.message(InterimState.waiting_card)
async def interim_card(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 3200\nПопробуй ещё раз:")
        return

    data  = await state.get_data()
    await state.clear()

    cash  = data.get("cash", 0)
    total = cash + amount
    now   = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")

    text = (
        f"Промежуточная выручка\n"
        f"Точка: {point}\n"
        f"Время: {now} (МСК)\n"
        f"Сотрудник: {user.full_name}\n"
        f"────────────────────\n"
        f"Наличные в кассе: {fmt(cash)}\n"
        f"Безнал с начала:  {fmt(amount)}\n"
        f"Итого:            {fmt(total)}"
    )

    await message.answer(
        "Отправил владельцу!\n\n" + text,
        reply_markup=employee_keyboard(),
    )
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

# ─── Предложение от сотрудника ────────────────────────────────────────────────

@router.message(F.text == "💡 Предложение", is_employee)
async def suggestion_start(message: Message, state: FSMContext):
    await state.set_state(SuggestionState.waiting_text)
    await message.answer(
        "Напиши своё предложение:\n\n"
        "Это может быть новый рецепт, идея заказать товар,\n"
        "улучшение для точки — всё что считаешь важным.\n\n"
        "Пиши в свободной форме:",
        reply_markup=ReplyKeyboardRemove(),
    )

@router.message(SuggestionState.waiting_text)
async def suggestion_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")
    now   = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")

    text = (
        f"Предложение от сотрудника\n"
        f"Точка: {point}\n"
        f"От: {user.full_name}\n"
        f"Время: {now} (МСК)\n"
        f"────────────────────\n"
        f"{message.text}"
    )

    await message.answer(
        "Предложение отправлено! Спасибо за инициативу 👍",
        reply_markup=employee_keyboard(),
    )
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
