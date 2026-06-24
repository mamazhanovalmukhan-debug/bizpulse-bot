import logging
import uuid
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import types
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import OWNER_ID, EMPLOYEE_POINTS, MSK
from storage import add_delivery, get_delivery, update_delivery, cancel_delivery, get_all_deliveries

router = Router()
scheduler = AsyncIOScheduler()

class AddDeliveryState(StatesGroup):
    supplier   = State()
    amount     = State()
    date_time  = State()
    comment    = State()

class ConfirmDeliveryState(StatesGroup):
    waiting_photo   = State()
    waiting_comment = State()

def is_owner(message: Message) -> bool:
    return message.from_user.id == OWNER_ID

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

def fmt(amount: float) -> str:
    return f"{int(amount):,}".replace(",", " ") + " р"

def parse_amount(text: str):
    cleaned = text.replace(" ", "").replace(",", ".").strip()
    try:
        val = float(cleaned)
        return val if val >= 0 else None
    except ValueError:
        return None

# ─── Владелец добавляет поставку ─────────────────────────────────────────────

def kb_cancel_owner():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )

@router.message(F.text == "Добавить поставку", is_owner)
async def owner_add_delivery(message: Message, state: FSMContext):
    await state.set_state(AddDeliveryState.supplier)
    await message.answer(
        "Новая поставка\n\nОт кого поставка? Напиши название поставщика:\n\nНажми Отмена чтобы выйти.",
        reply_markup=kb_cancel_owner(),
    )

@router.message(AddDeliveryState.supplier, is_owner)
async def step_supplier(message: Message, state: FSMContext):
    await state.update_data(supplier=message.text.strip())
    await state.set_state(AddDeliveryState.amount)
    await message.answer("На какую сумму?\nТолько цифры (или 0 если неизвестно):")

@router.message(AddDeliveryState.amount, is_owner)
async def step_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Только цифры, например: 15000\nПопробуй ещё раз:")
        return
    await state.update_data(amount=amount)
    await state.set_state(AddDeliveryState.date_time)
    await message.answer(
        "Когда ожидается поставка?\nНапиши дату и время:\nНапример: 25.06 14:00"
    )

@router.message(AddDeliveryState.date_time, is_owner)
async def step_datetime(message: Message, state: FSMContext):
    await state.update_data(date_time=message.text.strip())
    await state.set_state(AddDeliveryState.comment)
    await message.answer("Комментарий к поставке (что привезут):\nЕсли нет — напиши 0:")

@router.message(AddDeliveryState.comment, is_owner)
async def step_comment(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(comment=message.text.strip())
    data = await state.get_data()
    await state.clear()

    delivery_id = str(uuid.uuid4())[:8]
    now = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")

    delivery = {
        "id":        delivery_id,
        "supplier":  data.get("supplier", "?"),
        "amount":    data.get("amount", 0),
        "date_time": data.get("date_time", "?"),
        "comment":   data.get("comment", ""),
        "status":    "pending",  # pending / arrived / cancelled
        "created_at": now,
        "notified_count": 0,
    }
    add_delivery(delivery_id, delivery)

    text = (
        f"ПОСТАВКА СОЗДАНА\n"
        f"ID: {delivery_id}\n"
        f"Поставщик: {delivery['supplier']}\n"
        f"Сумма: {fmt(delivery['amount'])}\n"
        f"Когда: {delivery['date_time']}\n"
        f"Что: {delivery['comment'] if delivery['comment'] != '0' else 'Не указано'}"
    )

    # Уведомляем всех сотрудников
    for user_id, point in EMPLOYEE_POINTS.items():
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Поставка пришла", callback_data=f"delivery_arrived:{delivery_id}:{user_id}"),
                InlineKeyboardButton(text="Ещё не пришла",  callback_data=f"delivery_pending:{delivery_id}:{user_id}"),
            ]])
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"ОЖИДАЕТСЯ ПОСТАВКА\n\n"
                    f"Поставщик: {delivery['supplier']}\n"
                    f"Сумма: {fmt(delivery['amount'])}\n"
                    f"Время: {delivery['date_time']}\n"
                    f"Что: {delivery['comment'] if delivery['comment'] != '0' else 'Не указано'}"
                ),
                reply_markup=kb,
            )
        except Exception as e:
            logging.error(f"Ошибка уведомления сотрудника {user_id}: {e}")

    from aiogram.types import ReplyKeyboardMarkup as RKM, KeyboardButton as KB
    owner_kb = RKM(keyboard=[
        [KB(text="Добавить поставку"), KB(text="Поставки")],
        [KB(text="Статус сейчас"), KB(text="Итоги дня")],
        [KB(text="ИИ-анализ дня"), KB(text="Разведка")],
        [KB(text="Анализ остатков"), KB(text="Итоги недели")],
    ], resize_keyboard=True)

    await message.answer("Поставка добавлена! Сотрудники уведомлены.\n\n" + text, reply_markup=owner_kb)

    # Планируем напоминание через 1 час
    _schedule_delivery_check(bot, delivery_id)

# ─── Напоминание о поставке ──────────────────────────────────────────────────

def _schedule_delivery_check(bot: Bot, delivery_id: str):
    """Планируем проверку поставки через 1 час."""
    from apscheduler.triggers.interval import IntervalTrigger
    from datetime import timedelta
    scheduler.add_job(
        _remind_delivery,
        trigger="date",
        run_date=datetime.now() + __import__("datetime").timedelta(hours=1),
        args=[bot, delivery_id],
        id=f"delivery_{delivery_id}",
        replace_existing=True,
    )

async def _remind_delivery(bot: Bot, delivery_id: str):
    """Напоминаем сотрудникам если поставка ещё не пришла."""
    delivery = get_delivery(delivery_id)
    if not delivery or delivery.get("status") != "pending":
        return

    count = delivery.get("notified_count", 0)
    update_delivery(delivery_id, {"notified_count": count + 1})

    for user_id in EMPLOYEE_POINTS:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Поставка пришла", callback_data=f"delivery_arrived:{delivery_id}:{user_id}"),
                InlineKeyboardButton(text="Ещё не пришла",  callback_data=f"delivery_pending:{delivery_id}:{user_id}"),
            ]])
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"НАПОМИНАНИЕ: ожидается поставка\n\n"
                    f"Поставщик: {delivery['supplier']}\n"
                    f"Должна прийти: {delivery['date_time']}\n\n"
                    "Поставка пришла?"
                ),
                reply_markup=kb,
            )
        except Exception as e:
            logging.error(f"Ошибка напоминания: {e}")

    # Уведомляем владельца
    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"Поставка от {delivery['supplier']} ещё не подтверждена.\nДолжна прийти: {delivery['date_time']}",
        )
    except Exception as e:
        logging.error(f"Ошибка: {e}")

    # Планируем следующее напоминание ещё через час
    _schedule_delivery_check(bot, delivery_id)

# ─── Сотрудник подтверждает / отклоняет поставку ────────────────────────────

@router.callback_query(F.data.startswith("delivery_arrived:"))
async def delivery_arrived_cb(callback: types.CallbackQuery, state: FSMContext):
    parts       = callback.data.split(":")
    delivery_id = parts[1]
    employee_id = int(parts[2])

    if callback.from_user.id != employee_id and callback.from_user.id not in EMPLOYEE_POINTS:
        await callback.answer("Нет доступа.")
        return

    delivery = get_delivery(delivery_id)
    if not delivery or delivery.get("status") != "pending":
        await callback.answer("Поставка уже обработана.")
        return

    await callback.message.edit_text(callback.message.text + "\n\nПодтверждаю получение...")
    await state.update_data(delivery_id=delivery_id)
    await state.set_state(ConfirmDeliveryState.waiting_photo)

    await callback.message.answer(
        "Отправь фото поставки (накладная или товар).\nЕсли нет фото — напиши 0:"
    )
    await callback.answer()

@router.message(ConfirmDeliveryState.waiting_photo)
async def delivery_photo(message: Message, state: FSMContext):
    has_photo = message.photo is not None
    await state.update_data(has_photo=has_photo, photo_id=message.photo[-1].file_id if has_photo else None)
    await state.set_state(ConfirmDeliveryState.waiting_comment)
    await message.answer("От кого поставщик и любой комментарий:\nНапример: ООО Молоко, всё в порядке")

@router.message(ConfirmDeliveryState.waiting_comment)
async def delivery_confirm_comment(message: Message, state: FSMContext, bot: Bot):
    data        = await state.get_data()
    delivery_id = data.get("delivery_id")
    has_photo   = data.get("has_photo", False)
    photo_id    = data.get("photo_id")
    await state.clear()

    delivery = get_delivery(delivery_id)
    if not delivery:
        await message.answer("Поставка не найдена.")
        return

    update_delivery(delivery_id, {"status": "arrived", "comment_on_arrival": message.text})

    # Отменяем напоминания
    try:
        scheduler.remove_job(f"delivery_{delivery_id}")
    except Exception:
        pass

    now  = datetime.now(MSK).strftime("%d.%m.%Y, %H:%M")
    user = message.from_user

    report = (
        f"ПОСТАВКА ПОЛУЧЕНА\n\n"
        f"Поставщик: {delivery['supplier']}\n"
        f"Сумма: {fmt(delivery['amount'])}\n"
        f"Время получения: {now} МСК\n"
        f"Принял: {user.full_name}\n"
        f"Комментарий: {message.text}"
    )

    await message.answer("Поставка подтверждена! Отчет отправлен владельцу.", reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открытие смены")],
            [KeyboardButton(text="Закрытие смены")],
            [KeyboardButton(text="Промежуточная выручка")],
            [KeyboardButton(text="Предложение")],
        ],
        resize_keyboard=True,
    ))

    try:
        if has_photo and photo_id:
            await bot.send_photo(chat_id=OWNER_ID, photo=photo_id, caption=report)
        else:
            await bot.send_message(chat_id=OWNER_ID, text=report)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

@router.callback_query(F.data.startswith("delivery_pending:"))
async def delivery_pending_cb(callback: types.CallbackQuery, bot: Bot):
    parts       = callback.data.split(":")
    delivery_id = parts[1]
    await callback.message.edit_text(callback.message.text + "\n\nОтметил: ещё не пришла.")
    delivery = get_delivery(delivery_id)
    if delivery:
        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"Сотрудник сообщает: поставка от {delivery['supplier']} ещё не пришла.",
            )
        except Exception as e:
            logging.error(f"Ошибка: {e}")
    await callback.answer("Записал.")

# ─── Владелец отменяет поставку ──────────────────────────────────────────────

@router.message(F.text == "Поставки", is_owner)
async def list_deliveries(message: Message):
    deliveries = get_all_deliveries()
    if not deliveries:
        await message.answer("Поставок нет.")
        return

    lines = []
    kb_buttons = []
    for d_id, d in deliveries.items():
        status = {"pending": "ожидается", "arrived": "получена", "cancelled": "отменена"}.get(d.get("status"), "?")
        lines.append(f"{d['supplier']} — {d['date_time']} — {status}")
        if d.get("status") == "pending":
            kb_buttons.append([InlineKeyboardButton(
                text=f"Отменить: {d['supplier']}",
                callback_data=f"cancel_delivery:{d_id}"
            )])

    text = "ПОСТАВКИ\n\n" + "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons) if kb_buttons else None
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data.startswith("cancel_delivery:"))
async def cancel_delivery_cb(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет доступа.")
        return
    delivery_id = callback.data.split(":")[1]
    delivery    = get_delivery(delivery_id)
    if not delivery:
        await callback.answer("Не найдено.")
        return

    cancel_delivery(delivery_id)
    try:
        scheduler.remove_job(f"delivery_{delivery_id}")
    except Exception:
        pass

    await callback.message.edit_text(callback.message.text + f"\n\nПоставка от {delivery['supplier']} отменена.")
    for user_id in EMPLOYEE_POINTS:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"Поставка от {delivery['supplier']} ({delivery['date_time']}) отменена владельцем.",
            )
        except Exception as e:
            logging.error(f"Ошибка: {e}")
    await callback.answer("Отменено.")
