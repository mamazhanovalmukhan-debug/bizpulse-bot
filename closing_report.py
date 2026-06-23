import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from aiogram import types
from config import OWNER_ID, EMPLOYEE_POINTS, MSK
from storage import save_report, get_last_cash_balance

router = Router()

# Хранилище запросов на принудительное закрытие
_force_close_requests: dict[int, dict] = {}

class ClosingReport(StatesGroup):
    cash_revenue  = State()  # Выручка наличными за день
    card_revenue  = State()  # Выручка безнал
    cash_balance  = State()  # Остаток в кассе на конец
    expenses      = State()  # Расходы
    stock_notes   = State()  # Остатки
    staff         = State()  # Кто был на смене
    comment       = State()  # Комментарий

class ForceCloseState(StatesGroup):
    waiting_reason = State()

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
        if val < 0:
            return None
        return val
    except ValueError:
        return None

def fmt(amount: float) -> str:
    return f"{amount:,.0f} р".replace(",", " ")

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

def is_owner(message: Message) -> bool:
    return message.from_user.id == OWNER_ID

# ─── Обычное закрытие ─────────────────────────────────────────────────────────

@router.message(F.text.in_(["/закрытие", "🌙 Закрытие смены"]), is_employee)
async def cmd_start(message: Message, state: FSMContext):
    now_hour = datetime.now(MSK).hour
    # Если пытаются закрыть раньше 20:00 МСК — просим подтверждение босса
    if now_hour < 20:
        await state.set_state(ForceCloseState.waiting_reason)
        user  = message.from_user
        point = EMPLOYEE_POINTS.get(user.id, "?")
        now   = datetime.now(MSK).strftime("%H:%M")

        # Запрашиваем разрешение у владельца
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Разрешить закрытие",
                callback_data=f"approve_close:{user.id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"reject_close:{user.id}"
            ),
        ]])
        await message.answer(
            f"Сейчас {now} МСК — рано для закрытия.\n\n"
            "Отправляю запрос владельцу на принудительное закрытие.\n"
            "Напиши причину закрытия раньше времени:"
        )
        _force_close_requests[user.id] = {
            "name":  user.full_name,
            "point": point,
            "time":  now,
            "bot":   None,
        }
        return

    await state.clear()
    await state.set_state(ClosingReport.cash_revenue)
    await message.answer(
        "Закрытие смены\n\nСколько наличных принято за сегодня (выручка)?\nВведи только цифры:",
        reply_markup=ReplyKeyboardRemove(),
    )

# ─── Принудительное закрытие — причина ───────────────────────────────────────

@router.message(ForceCloseState.waiting_reason, is_employee)
async def force_close_reason(message: Message, state: FSMContext, bot: Bot):
    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")
    reason = message.text

    if user.id in _force_close_requests:
        _force_close_requests[user.id]["reason"] = reason
        _force_close_requests[user.id]["bot"] = bot

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Разрешить закрытие",
            callback_data=f"approve_close:{user.id}"
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=f"reject_close:{user.id}"
        ),
    ]])

    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"Запрос на досрочное закрытие\n\n"
                f"Сотрудник: {user.full_name}\n"
                f"Точка: {point}\n"
                f"Время: {_force_close_requests[user.id]['time']} МСК\n"
                f"Причина: {reason}"
            ),
            reply_markup=kb,
        )
    except Exception as e:
        logging.error(f"Ошибка запроса: {e}")

    await message.answer(
        "Запрос отправлен владельцу.\nОжидай подтверждения."
    )
    await state.clear()

# ─── Владелец одобряет/отклоняет ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("approve_close:"))
async def approve_close(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет доступа.")
        return
    employee_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Закрытие разрешено"
    )
    try:
        await bot.send_message(
            chat_id=employee_id,
            text=(
                "Владелец разрешил досрочное закрытие.\n\n"
                "Нажми 🌙 Закрытие смены ещё раз чтобы заполнить отчёт."
            ),
            reply_markup=employee_keyboard(),
        )
    except Exception as e:
        logging.error(f"Ошибка уведомления: {e}")
    await callback.answer("Закрытие разрешено.")

@router.callback_query(F.data.startswith("reject_close:"))
async def reject_close(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет доступа.")
        return
    employee_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ Закрытие отклонено"
    )
    try:
        await bot.send_message(
            chat_id=employee_id,
            text="Владелец отклонил досрочное закрытие. Продолжай смену.",
            reply_markup=employee_keyboard(),
        )
    except Exception as e:
        logging.error(f"Ошибка уведомления: {e}")
    await callback.answer("Закрытие отклонено.")

# ─── Шаги закрытия ───────────────────────────────────────────────────────────

@router.message(ClosingReport.cash_revenue)
async def step_cash_revenue(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 12400\nПопробуй ещё раз:")
        return
    await state.update_data(cash_revenue=amount)
    await state.set_state(ClosingReport.card_revenue)
    await message.answer(
        f"Выручка нал: {fmt(amount)}\n\nСколько прошло по безналу (терминал)?\nВведи только цифры:"
    )

@router.message(ClosingReport.card_revenue)
async def step_card_revenue(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 8750\nПопробуй ещё раз:")
        return
    data  = await state.get_data()
    total = data["cash_revenue"] + amount
    await state.update_data(card_revenue=amount)
    await state.set_state(ClosingReport.cash_balance)
    await message.answer(
        f"Безнал: {fmt(amount)}\n"
        f"Итого выручка: {fmt(total)}\n\n"
        "Сколько наличных осталось в кассе сейчас?\n"
        "Введи только цифры:"
    )

@router.message(ClosingReport.cash_balance)
async def step_cash_balance(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 7200\nПопробуй ещё раз:")
        return

    data          = await state.get_data()
    opening_cash  = get_last_cash_balance()
    cash_revenue  = data.get("cash_revenue", 0)
    expected      = opening_cash + cash_revenue
    diff          = amount - expected

    await state.update_data(cash_balance=amount)

    # Проверяем несходимость остатка
    if abs(diff) > 10:
        direction = "больше" if diff > 0 else "меньше"
        user  = message.from_user
        point = EMPLOYEE_POINTS.get(user.id, "?")
        alert = (
            f"Несходимость остатка кассы на закрытии!\n\n"
            f"Точка: {point}\n"
            f"Сотрудник: {user.full_name}\n\n"
            f"Касса на открытие:  {fmt(opening_cash)}\n"
            f"Выручка нал:        {fmt(cash_revenue)}\n"
            f"Ожидаемый остаток:  {fmt(expected)}\n"
            f"Фактический остаток:{fmt(amount)}\n"
            f"Разница: {fmt(abs(diff))} ({direction})"
        )
        await message.answer(
            f"Внимание! Несходимость кассы.\n\n"
            f"Ожидалось: {fmt(expected)}\n"
            f"Фактически: {fmt(amount)}\n"
            f"Разница: {fmt(abs(diff))} ({direction})\n\n"
            "Владелец уведомлён."
        )
        try:
            await bot.send_message(chat_id=OWNER_ID, text=alert)
        except Exception as e:
            logging.error(f"Ошибка алерта: {e}")

    await state.set_state(ClosingReport.expenses)
    await message.answer(
        f"Остаток: {fmt(amount)}\n\n"
        "Были расходы? Напиши сумму и на что:\n"
        "Например: 1200 — стаканы\n\nЕсли нет — Пропустить.",
        reply_markup=kb_skip(),
    )

@router.message(ClosingReport.expenses)
async def step_expenses(message: Message, state: FSMContext):
    await state.update_data(expenses=message.text)
    await state.set_state(ClosingReport.stock_notes)
    await message.answer(
        "Записал.\n\nЧто заканчивается или нужно заказать?\n"
        "Например: молоко, стаканы\n\nЕсли всё ок — Пропустить.",
        reply_markup=kb_skip(),
    )

@router.message(ClosingReport.stock_notes)
async def step_stock(message: Message, state: FSMContext):
    await state.update_data(stock_notes=message.text)
    await state.set_state(ClosingReport.staff)
    await message.answer(
        "Записал.\n\nКто был на смене сегодня?\n"
        "Напиши имена всех сотрудников:",
        reply_markup=ReplyKeyboardRemove(),
    )

@router.message(ClosingReport.staff)
async def step_staff(message: Message, state: FSMContext):
    await state.update_data(staff=message.text)
    await state.set_state(ClosingReport.comment)
    await message.answer(
        "Записал.\n\nКомментарий к смене (необязательно):\n"
        "Например: был наплыв туристов, работали без перерыва\n\nЕсли нет — Пропустить.",
        reply_markup=kb_skip(),
    )

@router.message(ClosingReport.comment)
async def step_comment(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(comment=message.text)
    data  = await state.get_data()
    await state.clear()

    user  = message.from_user
    point = EMPLOYEE_POINTS.get(user.id, "?")
    now   = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")

    cash_rev  = data.get("cash_revenue", 0)
    card_rev  = data.get("card_revenue", 0)
    balance   = data.get("cash_balance", 0)
    expenses  = data.get("expenses", "").strip()
    stock     = data.get("stock_notes", "").strip()
    staff     = data.get("staff", "").strip()
    comment   = data.get("comment", "").strip()
    total     = cash_rev + card_rev

    text = (
        f"Закрытие смены\n"
        f"Точка: {point}\n"
        f"Дата: {now} (МСК)\n"
        f"────────────────────\n"
        f"Выручка нал:     {fmt(cash_rev)}\n"
        f"Выручка безнал:  {fmt(card_rev)}\n"
        f"Итого выручка:   {fmt(total)}\n"
        f"Остаток в кассе: {fmt(balance)}\n"
        f"────────────────────\n"
        f"Расходы: {expenses if expenses and expenses != 'Пропустить' else 'Нет'}\n"
        f"Остатки: {stock if stock and stock != 'Пропустить' else 'Без замечаний'}\n"
        f"────────────────────\n"
        f"Смену вели: {staff}\n"
        f"Комментарий: {comment if comment and comment != 'Пропустить' else 'Нет'}"
    )

    save_report({
        "type":         "closing",
        "point":        point,
        "employee":     user.full_name,
        "cash":         cash_rev,
        "card":         card_rev,
        "cash_balance": balance,
        "expenses":     expenses,
        "stock_notes":  stock,
        "staff":        staff,
        "comment":      comment,
    })

    await message.answer(
        "Отчёт отправлен! Хорошей ночи 🌙\n\n" + text,
        reply_markup=employee_keyboard(),
    )
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

@router.message(F.text.in_(["/закрытие", "🌙 Закрытие смены"]))
async def cmd_denied(message: Message):
    await message.answer("У вас нет доступа к этой команде.")
