"""Универсальная отмена FSM + fallback для новых пользователей."""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, StateFilter
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

    # Пункт 3: новый пользователь без бизнеса — внятный ответ
    await message.answer(
        "Регистрация отменена.\n\n"
        "Чтобы начать заново, нажмите /start",
        reply_markup=__import__('aiogram').types.ReplyKeyboardRemove()
    )


# Пункт 3: fallback для новых пользователей без FSM-состояния
# Ставим priority=1 чтобы другие роутеры перехватывали первыми
@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def fallback_new_user(message: Message, state: FSMContext):
    """
    Если пользователь не в FSM-состоянии, не owner и не сотрудник —
    подсказываем как начать.
    """
    biz = await get_business_by_owner(message.from_user.id)
    if biz:
        return  # владелец — не наш случай

    bu = await get_business_user(message.from_user.id)
    if bu:
        return  # сотрудник — не наш случай

    # Новый пользователь без состояния пишет что-то непонятное
    await message.answer(
        "Чтобы начать регистрацию, нажмите /start"
    )
