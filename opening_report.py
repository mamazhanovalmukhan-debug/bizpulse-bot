import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import OWNER_ID, EMPLOYEE_POINTS
from storage import save_report

router = Router()

class OpeningReport(StatesGroup):
    cash_start = State()
    staff      = State()
    notes      = State()

def kb_skip():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True, one_time_keyboard=True,
    )

def kb_all_ok():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Всё в порядке")]],
        resize_keyboard=True, one_time_keyboard=True,
    )

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

def parse_amount(text):
    try:
        return float(text.replace(" ", "").replace(",", ".").strip())
    except ValueError:
        return None

def fmt(amount):
    return f"{amount:,.0f} р".replace(",", " ")

def build_report(data, name, point):
    now   = datetime.now().strftime("%d.%m.%Y, %H:%M")
    cash  = data.get("cash_start", 0.0)
    staff = data.get("staff", "").strip()
    notes = data.get("notes", "").strip()
    return (
        f"Открытие смены\n"
        f"Точка: {point}\n"
        f"Время: {now}\n"
        f"Сотрудник: {name}\n"
        f"────────────────────\n"
        f"Касса на начало: {fmt(cash)}\n"
        f"Персонал: {staff if staff and staff != 'Пропустить' else 'Не указано'}\n"
        f"Замечания: {notes if notes and notes not in ('Пропустить', 'Всё в порядке') else 'Нет'}"
    )

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

@router.message(F.text.in_(["/открытие", "🌅 Открытие смены"]), is_employee)
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OpeningReport.cash_start)
    await message.answer(
        "Открытие смены\n\nСколько денег в кассе на начало смены?",
        reply_markup=ReplyKeyboardRemove(),
    )

@router.message(OpeningReport.cash_start)
async def step_cash(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Введи сумму числом, например: 5000")
        return
    await state.update_data(cash_start=amount)
    await state.set_state(OpeningReport.staff)
    await message.answer(
        f"Касса: {fmt(amount)}\n\nКто сегодня работает?\n"
        "Например: Алина, Дамир\n\nЕсли один — Пропустить.",
        reply_markup=kb_skip(),
    )

@router.message(OpeningReport.staff)
async def step_staff(message: Message, state: FSMContext):
    await state.update_data(staff=message.text)
    await state.set_state(OpeningReport.notes)
    await message.answer(
        "Записал.\n\nЕсть замечания при открытии?\n"
        "Например: не пришла поставка\n\nЕсли всё ок — нажми кнопку.",
        reply_markup=kb_all_ok(),
    )

@router.message(OpeningReport.notes)
async def step_notes(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(notes=message.text)
    data  = await state.get_data()
    await state.clear()
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "Неизвестная точка")
    text  = build_report(data, user.full_name, point)
    save_report({
        "type": "opening", "point": point,
        "employee": user.full_name,
        "cash_open": data.get("cash_start", 0),
        "staff": data.get("staff", ""),
        "notes": data.get("notes", ""),
    })
    # Возвращаем меню сотрудника
    await message.answer(
        "Отчёт об открытии отправлен! Удачной смены 💪\n\n" + text,
        reply_markup=employee_keyboard(),
    )
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

@router.message(F.text.in_(["/открытие", "🌅 Открытие смены"]))
async def cmd_denied(message: Message):
    await message.answer("У вас нет доступа к этой команде.")
