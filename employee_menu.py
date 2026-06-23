import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import EMPLOYEE_POINTS, OWNER_ID, MSK
from storage import get_last_cash_balance, set_last_interim_cash

router = Router()

class InterimState(StatesGroup):
    waiting_cash     = State()
    waiting_card     = State()
    waiting_expenses = State()

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
        return val if val >= 0 else None
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
    # Показываем текущий минимальный порог
    from storage import get_last_interim_cash
    current_min = get_last_interim_cash()
    hint = f"\n\nМинимум в кассе сейчас должно быть: {fmt(current_min)}" if current_min > 0 else ""
    await message.answer(
        f"Промежуточная выручка{hint}\n\nСколько сейчас наличных в кассе?\nТолько цифры:",
        reply_markup=ReplyKeyboardRemove(),
    )

@router.message(InterimState.waiting_cash)
async def interim_cash(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 8500\nПопробуй ещё раз:")
        return

    from storage import get_last_interim_cash
    min_expected = get_last_interim_cash()
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")

    # Наличных не может быть меньше чем в предыдущем промежутке
    if amount < min_expected - 10:
        alert = (
            f"Наличных стало меньше!\n\n"
            f"Точка: {point}\n"
            f"Сотрудник: {user.full_name}\n"
            f"Время: {datetime.now(MSK).strftime('%H:%M')} МСК\n\n"
            f"Предыдущий промежуток: {fmt(min_expected)}\n"
            f"Сейчас: {fmt(amount)}\n"
            f"Не хватает: {fmt(min_expected - amount)}"
        )
        await message.answer(
            f"Внимание! Наличных меньше чем было.\n\n"
            f"Было: {fmt(min_expected)}\n"
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
        f"Наличные: {fmt(amount)}\n\nСколько прошло по безналу с начала смены?\nЕсли не знаешь — напиши 0:"
    )

@router.message(InterimState.waiting_card)
async def interim_card(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 3200\nПопробуй ещё раз:")
        return
    await state.update_data(card=amount)
    await state.set_state(InterimState.waiting_expenses)
    await message.answer(
        f"Безнал: {fmt(amount)}\n\nБыли расходы за эту часть смены?\n"
        "Напиши сумму и на что, например: 500 — салфетки\n\nЕсли нет — напиши 0:",
    )

@router.message(InterimState.waiting_expenses)
async def interim_expenses(message: Message, state: FSMContext, bot: Bot):
    # Принимаем и текст и 0
    expenses_text = message.text.strip()
    data  = await state.get_data()
    await state.clear()

    cash  = data.get("cash", 0)
    card  = data.get("card", 0)
    total = cash + card
    now   = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")

    # Обновляем минимальный порог наличных
    set_last_interim_cash(cash)

    exp_line = expenses_text if expenses_text and expenses_text != "0" else "Нет"

    text = (
        f"Промежуточная выручка\n"
        f"Точка: {point}\n"
        f"Время: {now} (МСК)\n"
        f"Сотрудник: {user.full_name}\n"
        f"────────────────────\n"
        f"Наличные в кассе: {fmt(cash)}\n"
        f"Безнал с начала:  {fmt(card)}\n"
        f"Итого:            {fmt(total)}\n"
        f"Расходы:          {exp_line}"
    )

    await message.answer("Отправил владельцу!\n\n" + text, reply_markup=employee_keyboard())
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

# ─── Предложение ──────────────────────────────────────────────────────────────

@router.message(F.text == "💡 Предложение", is_employee)
async def suggestion_start(message: Message, state: FSMContext):
    await state.set_state(SuggestionState.waiting_text)
    await message.answer(
        "Напиши своё предложение:\n\n"
        "Новый рецепт, заказать товар, улучшение — всё что считаешь важным.\n\n"
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

    await message.answer("Предложение отправлено! Спасибо 👍", reply_markup=employee_keyboard())
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
