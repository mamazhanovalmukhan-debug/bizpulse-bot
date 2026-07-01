"""Универсальная отмена FSM."""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from database.models import get_business_by_owner, get_business_user
from keyboards.owner import owner_main_kb
from keyboards.employee import employee_main_kb

router = Router()

@router.message(F.text.lower().in_(["отмена", "назад", "/cancel"]))
async def cancel_any(message: Message, state: FSMContext):
    current = await state.get_state()
    await state.clear()
    biz = await get_business_by_owner(message.from_user.id)
    if biz:
        await message.answer(
            "Действие отменено." if current else "Главное меню:",
            reply_markup=owner_main_kb()
        )
        return
    bu = await get_business_user(message.from_user.id)
    if bu:
        await message.answer(
            "Действие отменено." if current else "Главное меню:",
            reply_markup=employee_main_kb()
        )
        return
    await message.answer("Действие отменено.")
