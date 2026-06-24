import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import OWNER_ID, EMPLOYEE_POINTS, MSK
from storage import save_report, get_yesterday_closing, set_opening_cash, get_today_summary

router = Router()

class OpeningReport(StatesGroup):
    cash_start = State()
    staff      = State()
    notes      = State()

def kb_skip():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пропустить")],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True, one_time_keyboard=True,
    )

def kb_all_ok():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Все в порядке")],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True, one_time_keyboard=True,
    )

def kb_cancel():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )

def employee_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открытие смены")],
            [KeyboardButton(text="Закрытие смены")],
            [KeyboardButton(text="Промежуточная выручка")],
            [KeyboardButton(text="Предложение")],
        ],
        resize_keyboard=True,
    )

def parse_amount(text: str):
    cleaned = text.replace(" ", "").replace(",", ".").strip()
    try:
        val = float(cleaned)
        return val if val >= 0 else None
    except ValueError:
        return None

def fmt(amount: float) -> str:
    return f"{int(amount):,}".replace(",", " ") + " р"

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

def validate_staff_name(text: str) -> bool:
    """Имя должно быть минимум 2 символа и содержать хотя бы одну букву."""
    text = text.strip()
    if len(text) < 2:
        return False
    return any(c.isalpha() for c in text)

@router.message(F.text.in_(["/открытие", "Открытие смены"]), is_employee)
async def cmd_start(message: Message, state: FSMContext):
    summary = get_today_summary()
    if summary["opened"]:
        await message.answer("Смена уже открыта сегодня.", reply_markup=employee_keyboard())
        return

    await state.clear()
    await state.set_state(OpeningReport.cash_start)

    yesterday = get_yesterday_closing()
    hint = ""
    if yesterday:
        bal = yesterday.get("cash_balance", 0)
        hint = f"\n\nВчера на закрытие в кассе было: {fmt(bal)}"

    await message.answer(
        f"Открытие смены{hint}\n\nСколько наличных в кассе прямо сейчас?\nТолько цифры:",
        reply_markup=kb_cancel(),
    )

@router.message(OpeningReport.cash_start)
async def step_cash(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 5000\nПопробуй ещё раз:")
        return

    yesterday = get_yesterday_closing()
    if yesterday:
        expected = yesterday.get("cash_balance", 0)
        diff     = amount - expected
        if abs(diff) > 10:
            direction = "больше" if diff > 0 else "меньше"
            user  = message.from_user
            point = EMPLOYEE_POINTS.get(user.id, "?")
            alert = (
                f"НЕСХОДИМОСТЬ КАССЫ НА ОТКРЫТИИ\n\n"
                f"Точка: {point}\n"
                f"Сотрудник: {user.full_name}\n"
                f"Время: {datetime.now(MSK).strftime('%H:%M')} МСК\n\n"
                f"Вчера на закрытие: {fmt(expected)}\n"
                f"Сегодня на открытие: {fmt(amount)}\n"
                f"Разница: {fmt(abs(diff))} ({direction})"
            )
            await message.answer(
                f"Внимание! Несходимость кассы.\n"
                f"Вчера было: {fmt(expected)}\n"
                f"Сейчас: {fmt(amount)}\n"
                f"Разница: {fmt(abs(diff))} ({direction})\n\n"
                "Владелец уведомлен."
            )
            try:
                await bot.send_message(chat_id=OWNER_ID, text=alert)
            except Exception as e:
                logging.error(f"Ошибка алерта: {e}")

    set_opening_cash(amount)
    await state.update_data(cash_start=amount)
    await state.set_state(OpeningReport.staff)
    await message.answer(
        f"Касса: {fmt(amount)}\n\nКто сегодня работает?\nНапример: Алина, Дамир\n\nЕсли один — Пропустить.",
        reply_markup=kb_skip(),
    )

@router.message(OpeningReport.staff)
async def step_staff(message: Message, state: FSMContext):
    text = message.text.strip()

    # Если не "Пропустить" — валидируем
    if text != "Пропустить" and not validate_staff_name(text):
        await message.answer(
            "Похоже, имя введено неверно.\n"
            "Напиши имя сотрудника (минимум 2 буквы), например: Алина\n"
            "Или нажми Пропустить:"
        )
        return

    await state.update_data(staff=text)
    await state.set_state(OpeningReport.notes)
    await message.answer(
        "Записал.\n\nЕсть замечания при открытии?\nНапример: не пришла поставка\n\nЕсли все ок:",
        reply_markup=kb_all_ok(),
    )

@router.message(OpeningReport.notes)
async def step_notes(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(notes=message.text)
    data  = await state.get_data()
    await state.clear()

    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")
    now   = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")
    cash  = data.get("cash_start", 0)
    staff = data.get("staff", "").strip()
    notes = data.get("notes", "").strip()

    text = (
        f"ОТКРЫТИЕ СМЕНЫ\n"
        f"Точка: {point}\n"
        f"Время: {now} МСК\n"
        f"Сотрудник: {user.full_name}\n"
        f"---\n"
        f"Касса на начало: {fmt(cash)}\n"
        f"Персонал: {staff if staff and staff != 'Пропустить' else 'Не указано'}\n"
        f"Замечания: {notes if notes and notes not in ('Пропустить', 'Все в порядке') else 'Нет'}"
    )

    save_report({
        "type": "opening", "point": point,
        "employee": user.full_name,
        "cash_open": cash, "staff": staff, "notes": notes,
    })

    await message.answer("Отчет об открытии отправлен! Удачной смены\n\n" + text, reply_markup=employee_keyboard())
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

@router.message(F.text.in_(["/открытие", "Открытие смены"]))
async def cmd_denied(message: Message):
    await message.answer("У вас нет доступа к этой команде.")
