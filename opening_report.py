import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import OWNER_ID, EMPLOYEE_POINTS, MSK
from storage import save_report, get_yesterday_closing, set_last_cash_balance, get_today_summary

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

def parse_amount(text: str):
    cleaned = text.replace(" ", "").replace(",", ".").strip()
    try:
        val = float(cleaned)
        return val if val >= 0 else None
    except ValueError:
        return None

def fmt(amount: float) -> str:
    return f"{amount:,.0f} р".replace(",", " ")

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

@router.message(F.text.in_(["/открытие", "🌅 Открытие смены"]), is_employee)
async def cmd_start(message: Message, state: FSMContext):
    summary = get_today_summary()

    # Блокировка повторного открытия
    if summary["opened"]:
        await message.answer(
            "Смена уже открыта сегодня.",
            reply_markup=employee_keyboard(),
        )
        return

    await state.clear()
    await state.set_state(OpeningReport.cash_start)

    yesterday = get_yesterday_closing()
    hint = ""
    if yesterday:
        hint = f"\n\nВчера на закрытие в кассе было: {fmt(yesterday.get('cash_balance', 0))}"

    await message.answer(
        f"Открытие смены\n\nСколько наличных в кассе прямо сейчас?{hint}\n\nТолько цифры:",
        reply_markup=ReplyKeyboardRemove(),
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
            alert = (
                f"Несходимость кассы на открытии!\n\n"
                f"Сотрудник: {message.from_user.full_name}\n"
                f"Точка: {EMPLOYEE_POINTS.get(message.from_user.id, '?')}\n\n"
                f"Вчера на закрытие: {fmt(expected)}\n"
                f"Сегодня на открытие: {fmt(amount)}\n"
                f"Разница: {fmt(abs(diff))} ({direction})"
            )
            await message.answer(
                f"Внимание! Несходимость кассы.\n\n"
                f"Вчера было: {fmt(expected)}\n"
                f"Сейчас: {fmt(amount)}\n"
                f"Разница: {fmt(abs(diff))} ({direction})\n\n"
                "Владелец уведомлён."
            )
            try:
                await bot.send_message(chat_id=OWNER_ID, text=alert)
            except Exception as e:
                logging.error(f"Ошибка алерта: {e}")

    set_last_cash_balance(amount)
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
    point = EMPLOYEE_POINTS.get(user.id, "?")
    now   = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")
    cash  = data.get("cash_start", 0)
    staff = data.get("staff", "").strip()
    notes = data.get("notes", "").strip()

    text = (
        f"Открытие смены\n"
        f"Точка: {point}\n"
        f"Время: {now} (МСК)\n"
        f"Сотрудник: {user.full_name}\n"
        f"────────────────────\n"
        f"Касса на начало: {fmt(cash)}\n"
        f"Персонал: {staff if staff and staff != 'Пропустить' else 'Не указано'}\n"
        f"Замечания: {notes if notes and notes not in ('Пропустить', 'Всё в порядке') else 'Нет'}"
    )

    save_report({
        "type": "opening", "point": point,
        "employee": user.full_name,
        "cash_open": cash, "staff": staff, "notes": notes,
    })

    await message.answer("Отчёт отправлен! Удачной смены 💪\n\n" + text, reply_markup=employee_keyboard())
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

@router.message(F.text.in_(["/открытие", "🌅 Открытие смены"]))
async def cmd_denied(message: Message):
    await message.answer("У вас нет доступа к этой команде.")
