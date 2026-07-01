"""Точка входа v6 — /start, invite-ссылки, self-repair подписки."""
import logging
from aiogram import Router
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from database.models import (
    get_business_by_owner, get_business_user, get_subscription
)
from keyboards.owner import owner_main_kb
from keyboards.employee import employee_main_kb
from services.invite_service import handle_invite

router = Router()
log    = logging.getLogger("start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    args = message.text.split(maxsplit=1)[1] if " " in message.text else ""

    # ── Invite-ссылка ────────────────────────────────────────────────────────
    if args.startswith("invite_"):
        token  = args[len("invite_"):]
        result = await handle_invite(
            token, user.id, user.full_name or "", user.username or ""
        )
        if not result["ok"]:
            await message.answer(
                f"❌ {result['reason']}\n\n"
                "Попросите владельца выслать новую ссылку.",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        role_text = "менеджера" if result["role"] == "manager" else "сотрудника"
        await message.answer(
            f"✅ Вы подключены к бизнесу в роли {role_text}!\n\n"
            "Теперь можете открывать смены и отправлять отчёты.",
            reply_markup=employee_main_kb()
        )
        return

    # ── Уже владелец ─────────────────────────────────────────────────────────
    biz = await get_business_by_owner(user.id)
    if biz:
        # Пункт 4: self-repair — проверяем наличие subscription
        await _ensure_subscription(biz["id"], user.id)
        await message.answer(
            f"С возвращением! 👋\n\nБизнес: {biz['name']}\n\nВыберите действие:",
            reply_markup=owner_main_kb()
        )
        return

    # ── Уже сотрудник ─────────────────────────────────────────────────────────
    bu = await get_business_user(user.id)
    if bu:
        await message.answer(
            "С возвращением!\n\nВыберите действие:",
            reply_markup=employee_main_kb()
        )
        return

    # ── Новый пользователь — онбординг ───────────────────────────────────────
    from handlers.onboarding import start_onboarding
    await start_onboarding(message, state)


async def _ensure_subscription(business_id: int, owner_id: int):
    """
    Пункт 4: self-repair. Если у бизнеса нет subscription — создаём.
    Это защита от ситуации когда бизнес создан но подписка не записалась.
    """
    try:
        sub = await get_subscription(business_id)
        if sub:
            return  # всё хорошо

        from database.models import has_used_trial, create_subscription, create_trial_usage
        from services.plan_service import set_business_plan
        from config import config

        from database.session import get_pool
        loc_count = await get_pool().fetchval(
            "SELECT COUNT(*) FROM locations WHERE business_id=$1 AND is_active=TRUE",
            business_id
        )
        loc_count = int(loc_count or 0)
        if loc_count <= 1:
            plan_code = "START"
        elif loc_count <= 5:
            plan_code = "GROW"
        else:
            plan_code = "NETWORK"

        used = await has_used_trial(owner_id)
        if not used:
            await create_subscription(business_id, config.DEFAULT_TRIAL_DAYS)
            await create_trial_usage(owner_id, business_id, config.DEFAULT_TRIAL_DAYS)
            await set_business_plan(business_id, plan_code)
            log.info(f"self-repair: created trial subscription for biz {business_id}")
        else:
            await get_pool().execute(
                """INSERT INTO subscriptions (business_id, status)
                   VALUES ($1, 'expired')
                   ON CONFLICT (business_id) DO NOTHING""",
                business_id
            )
            await set_business_plan(business_id, plan_code)
            log.info(f"self-repair: created expired subscription for biz {business_id}")
    except Exception as e:
        log.error(f"_ensure_subscription error for biz {business_id}: {e}")
