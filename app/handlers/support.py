"""Поддержка — подача и обработка тикетов."""
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import (
    create_ticket, get_business_by_owner, get_business_user
)
from services.notification_service import notify_admins, msg_support_ticket
from config import config

router = Router()

TICKET_TYPES = {
    "Техническая ошибка":    "technical",
    "Вопрос по оплате":      "payment",
    "Проблема с сотрудником": "employee",
    "Проблема с отчётом":    "report",
    "Другое":                 "other",
}

class SupportState(StatesGroup):
    ticket_type = State()
    message     = State()

def kb_ticket_types():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Техническая ошибка"),
             KeyboardButton(text="Вопрос по оплате")],
            [KeyboardButton(text="Проблема с сотрудником"),
             KeyboardButton(text="Проблема с отчётом")],
            [KeyboardButton(text="Другое"),
             KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True, one_time_keyboard=True
    )

def kb_cancel():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )

@router.message(Command("support"))
@router.message(F.text.in_(["🆘 Поддержка", "🆘 Помощь"]))
async def support_start(message: Message, state: FSMContext):
    user = message.from_user
    biz  = await get_business_by_owner(user.id)
    bu   = await get_business_user(user.id) if not biz else None
    bid  = biz["id"] if biz else (bu["business_id"] if bu else None)
    role = "owner" if biz else (bu["role"] if bu else "unknown")

    await state.update_data(business_id=bid, role=role)
    await state.set_state(SupportState.ticket_type)
    await message.answer(
        "🆘 Поддержка BizPulse\n\nВыберите тип проблемы:",
        reply_markup=kb_ticket_types()
    )

@router.message(SupportState.ticket_type)
async def support_type(message: Message, state: FSMContext):
    ttype = TICKET_TYPES.get(message.text)
    if not ttype:
        await message.answer("Выберите тип из списка:")
        return
    await state.update_data(ticket_type=ttype, ticket_type_name=message.text)
    await state.set_state(SupportState.message)
    await message.answer(
        f"Тип: {message.text} ✓\n\n"
        "Опишите проблему подробно:\n"
        "(что произошло, что делали, что увидели)",
        reply_markup=kb_cancel()
    )

@router.message(SupportState.message)
async def support_message(message: Message, state: FSMContext, bot=None):
    data = await state.get_data()
    await state.clear()

    user = message.from_user
    bid  = data.get("business_id")
    role = data.get("role", "unknown")
    ttype = data.get("ticket_type", "other")
    ttype_name = data.get("ticket_type_name", "")

    ticket_id = await create_ticket(bid, user.id, role, ttype, message.text.strip())

    biz_name = "неизвестно"
    if bid:
        from database.models import get_business
        biz = await get_business(bid)
        if biz:
            biz_name = biz["name"]

    await message.answer(
        f"✅ Заявка #{ticket_id} принята!\n\n"
        f"Мы ответим в ближайшее время.\n"
        f"Тип: {ttype_name}\n\n"
        f"Поддержка: {config.SUPPORT_USERNAME}\n"
        f"Ваш ID: {user.id}"
    )

    if bot:
        await notify_admins(
            bot,
            msg_support_ticket(ticket_id, biz_name, role, ttype_name, message.text)
        )
