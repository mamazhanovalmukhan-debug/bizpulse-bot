"""Точка входа — /start, invite-ссылки, приветствие."""
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from database.models import get_business_by_owner, get_business_user
from keyboards.owner import owner_main_kb
from keyboards.employee import employee_main_kb
from services.invite_service import handle_invite

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    args = message.text.split(maxsplit=1)[1] if " " in message.text else ""

    # Invite-ссылка
    if args.startswith("invite_"):
        token  = args[len("invite_"):]
        result = await handle_invite(token, user.id, user.full_name or "",
                                     user.username or "")
        if not result["ok"]:
            await message.answer(f"❌ {result['reason']}", reply_markup=ReplyKeyboardRemove())
            return
        role_text = "менеджера" if result["role"] == "manager" else "сотрудника"
        await message.answer(
            f"✅ Вы подключены к бизнесу в роли {role_text}!\n\n"
            f"Теперь вы можете открывать смены и отправлять отчёты.",
            reply_markup=employee_main_kb()
        )
        return

    # Уже владелец
    biz = await get_business_by_owner(user.id)
    if biz:
        await message.answer(
            f"С возвращением! 👋\n\nБизнес: {biz['name']}\n\nВыберите действие:",
            reply_markup=owner_main_kb()
        )
        return

    # Уже сотрудник
    bu = await get_business_user(user.id)
    if bu:
        await message.answer(
            "С возвращением!\n\nВыберите действие:",
            reply_markup=employee_main_kb()
        )
        return

    # Новый пользователь — онбординг
    from handlers.onboarding import start_onboarding
    await start_onboarding(message, state)
