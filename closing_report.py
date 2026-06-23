import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import types
from config import OWNER_ID, EMPLOYEE_POINTS, MSK
from storage import save_report, get_expected_closing_balance, get_opening_cash, get_today_summary

router = Router()

_approved_force_close: set[int] = set()

class ClosingReport(StatesGroup):
    cash_revenue = State()
    card_revenue = State()
    cash_balance = State()
    expenses     = State()
    stock_notes  = State()
    staff        = State()
    comment      = State()

class ForceCloseState(StatesGroup):
    waiting_reason = State()

def kb_skip():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True, one_time_keyboard=True,
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

def parse_expense(text: str):
    """Парсим расходы: '1200 стаканы' или '0' или 'Пропустить'."""
    if text.strip() in ("0", "Пропустить", "Нет"):
        return 0.0, text.strip()
    # Пробуем вытащить сумму из начала строки
    parts = text.strip().split(None, 1)
    try:
        amount = float(parts[0].replace(",", "."))
        desc   = parts[1] if len(parts) > 1 else ""
        return amount, text.strip()
    except (ValueError, IndexError):
        return 0.0, text.strip()

def fmt(amount: float) -> str:
    return f"{int(amount):,}".replace(",", " ") + " р"

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

@router.message(F.text.in_(["/закрытие", "Закрытие смены"]), is_employee)
async def cmd_start(message: Message, state: FSMContext):
    user    = message.from_user
    summary = get_today_summary()
    now_msk = datetime.now(MSK)

    if not summary["opened"]:
        await message.answer("Нельзя закрыть смену — она ещё не открыта.", reply_markup=employee_keyboard())
        return

    if summary["closed"]:
        await message.answer("Смена уже закрыта сегодня.", reply_markup=employee_keyboard())
        return

    if now_msk.hour < 20 and user.id not in _approved_force_close:
        await state.set_state(ForceCloseState.waiting_reason)
        await message.answer(
            f"Сейчас {now_msk.strftime('%H:%M')} МСК — рано для закрытия.\n\n"
            "Напиши причину закрытия раньше времени:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    _approved_force_close.discard(user.id)
    await state.clear()
    await state.set_state(ClosingReport.cash_revenue)
    await message.answer(
        "Закрытие смены\n\nСколько наличных принято за сегодня (только выручка, не считая остаток с утра)?\nТолько цифры:",
        reply_markup=ReplyKeyboardRemove(),
    )

@router.message(ForceCloseState.waiting_reason, is_employee)
async def force_close_reason(message: Message, state: FSMContext, bot: Bot):
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")
    now   = datetime.now(MSK).strftime("%H:%M")
    kb    = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Разрешить", callback_data=f"approve_close:{user.id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"reject_close:{user.id}"),
    ]])
    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"ЗАПРОС НА ДОСРОЧНОЕ ЗАКРЫТИЕ\n\n"
                f"Сотрудник: {user.full_name}\n"
                f"Точка: {point}\n"
                f"Время: {now} МСК\n"
                f"Причина: {message.text}"
            ),
            reply_markup=kb,
        )
    except Exception as e:
        logging.error(f"Ошибка: {e}")
    await message.answer("Запрос отправлен владельцу. Жди подтверждения.", reply_markup=employee_keyboard())
    await state.clear()

@router.callback_query(F.data.startswith("approve_close:"))
async def approve_close(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет доступа.")
        return
    employee_id = int(callback.data.split(":")[1])
    _approved_force_close.add(employee_id)
    await callback.message.edit_text(callback.message.text + "\n\nРазрешено.")
    try:
        await bot.send_message(
            chat_id=employee_id,
            text="Владелец разрешил досрочное закрытие.\nНажми Закрытие смены чтобы заполнить отчет.",
            reply_markup=employee_keyboard(),
        )
    except Exception as e:
        logging.error(f"Ошибка: {e}")
    await callback.answer("Разрешено.")

@router.callback_query(F.data.startswith("reject_close:"))
async def reject_close(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет доступа.")
        return
    employee_id = int(callback.data.split(":")[1])
    _approved_force_close.discard(employee_id)
    await callback.message.edit_text(callback.message.text + "\n\nОтклонено.")
    try:
        await bot.send_message(
            chat_id=employee_id,
            text="Владелец отклонил досрочное закрытие. Продолжай смену.",
            reply_markup=employee_keyboard(),
        )
    except Exception as e:
        logging.error(f"Ошибка: {e}")
    await callback.answer("Отклонено.")

@router.message(ClosingReport.cash_revenue)
async def step_cash_revenue(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 12400\nПопробуй ещё раз:")
        return
    await state.update_data(cash_revenue=amount)
    await state.set_state(ClosingReport.card_revenue)
    await message.answer(f"Выручка нал: {fmt(amount)}\n\nСколько по безналу (терминал)?\nТолько цифры:")

@router.message(ClosingReport.card_revenue)
async def step_card_revenue(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 8750\nПопробуй ещё раз:")
        return
    data  = await state.get_data()
    total = data["cash_revenue"] + amount
    await state.update_data(card_revenue=amount)
    await state.set_state(ClosingReport.expenses)
    await message.answer(
        f"Безнал: {fmt(amount)}\nИтого выручка: {fmt(total)}\n\n"
        "Были расходы? Напиши сумму и на что:\n1200 стаканы\n\nЕсли нет — Пропустить.",
        reply_markup=kb_skip(),
    )

@router.message(ClosingReport.expenses)
async def step_expenses(message: Message, state: FSMContext):
    expense_amount, expense_text = parse_expense(message.text)
    await state.update_data(expenses=expense_text, expense_amount=expense_amount)
    await state.set_state(ClosingReport.cash_balance)

    data     = await state.get_data()
    cash_rev = data.get("cash_revenue", 0)
    expected = get_expected_closing_balance(cash_rev, expense_amount)

    await message.answer(
        f"Записал.\n\nСколько наличных в кассе сейчас (остаток)?\n"
        f"Ожидается примерно: {fmt(expected)}\nТолько цифры:"
    )

@router.message(ClosingReport.cash_balance)
async def step_cash_balance(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 7200\nПопробуй ещё раз:")
        return

    data          = await state.get_data()
    cash_revenue  = data.get("cash_revenue", 0)
    expense_amount = data.get("expense_amount", 0)
    expected      = get_expected_closing_balance(cash_revenue, expense_amount)
    diff          = amount - expected

    await state.update_data(cash_balance=amount)

    if abs(diff) > 10:
        direction = "больше" if diff > 0 else "меньше"
        user  = message.from_user
        point = EMPLOYEE_POINTS.get(user.id, "?")
        alert = (
            f"НЕСХОДИМОСТЬ КАССЫ НА ЗАКРЫТИИ\n\n"
            f"Точка: {point}\n"
            f"Сотрудник: {user.full_name}\n\n"
            f"Касса на открытие: {fmt(get_opening_cash())}\n"
            f"Выручка нал: {fmt(cash_revenue)}\n"
            f"Расходы: {fmt(expense_amount)}\n"
            f"Ожидаемый остаток: {fmt(expected)}\n"
            f"Фактический остаток: {fmt(amount)}\n"
            f"Разница: {fmt(abs(diff))} ({direction})"
        )
        await message.answer(
            f"Внимание! Несходимость кассы.\n"
            f"Ожидалось: {fmt(expected)}\n"
            f"Фактически: {fmt(amount)}\n"
            f"Разница: {fmt(abs(diff))} ({direction})\n\n"
            "Владелец уведомлен."
        )
        try:
            await bot.send_message(chat_id=OWNER_ID, text=alert)
        except Exception as e:
            logging.error(f"Ошибка алерта: {e}")

    await state.set_state(ClosingReport.stock_notes)
    await message.answer(
        f"Остаток: {fmt(amount)}\n\nЧто заканчивается или нужно заказать?\nЕсли все ок — Пропустить.",
        reply_markup=kb_skip(),
    )

@router.message(ClosingReport.stock_notes)
async def step_stock(message: Message, state: FSMContext):
    await state.update_data(stock_notes=message.text)
    await state.set_state(ClosingReport.staff)
    await message.answer("Записал.\n\nКто был на смене сегодня?\nНапиши имена:", reply_markup=ReplyKeyboardRemove())

@router.message(ClosingReport.staff)
async def step_staff(message: Message, state: FSMContext):
    await state.update_data(staff=message.text)
    await state.set_state(ClosingReport.comment)
    await message.answer("Записал.\n\nКомментарий к смене (необязательно):\nЕсли нет — Пропустить.", reply_markup=kb_skip())

@router.message(ClosingReport.comment)
async def step_comment(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(comment=message.text)
    data = await state.get_data()
    await state.clear()

    user     = message.from_user
    point    = EMPLOYEE_POINTS.get(user.id, "?")
    now      = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")
    cash_rev = data.get("cash_revenue", 0)
    card_rev = data.get("card_revenue", 0)
    balance  = data.get("cash_balance", 0)
    expenses = data.get("expenses", "").strip()
    stock    = data.get("stock_notes", "").strip()
    staff    = data.get("staff", "").strip()
    comment  = data.get("comment", "").strip()

    text = (
        f"ЗАКРЫТИЕ СМЕНЫ\n"
        f"Точка: {point}\n"
        f"Дата: {now} МСК\n"
        f"---\n"
        f"Выручка нал:     {fmt(cash_rev)}\n"
        f"Выручка безнал:  {fmt(card_rev)}\n"
        f"Итого выручка:   {fmt(cash_rev + card_rev)}\n"
        f"Остаток в кассе: {fmt(balance)}\n"
        f"---\n"
        f"Расходы: {expenses if expenses and expenses not in ('Пропустить', '0') else 'Нет'}\n"
        f"Остатки: {stock if stock and stock != 'Пропустить' else 'Без замечаний'}\n"
        f"---\n"
        f"Смену вели: {staff}\n"
        f"Комментарий: {comment if comment and comment != 'Пропустить' else 'Нет'}"
    )

    save_report({
        "type": "closing", "point": point,
        "employee": user.full_name,
        "cash": cash_rev, "card": card_rev,
        "cash_balance": balance,
        "expenses": expenses, "stock_notes": stock,
        "staff": staff, "comment": comment,
    })

    await message.answer("Отчет отправлен! Хорошей ночи\n\n" + text, reply_markup=employee_keyboard())
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

@router.message(F.text.in_(["/закрытие", "Закрытие смены"]))
async def cmd_denied(message: Message):
    await message.answer("У вас нет доступа к этой команде.")
