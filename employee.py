"""Тариф и оплата v6 — план выбирается через InlineKeyboard + callback_data."""
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command
from database.models import (
    get_business_by_owner, get_subscription, get_locations
)
from services.plan_service import (
    PLANS, PLAN_ORDER, plan_list_text, plan_summary_text,
    get_business_plan, check_location_limit, location_limit_message
)
from services.payment_service import create_plan_invoice
from keyboards.owner import owner_main_kb

router = Router()


# ── Inline-клавиатура выбора тарифа ─────────────────────────────────────────

def plan_inline_kb(current_code: str = "") -> InlineKeyboardMarkup:
    """
    MED-4 FIX: plan_code передаётся через callback_data, а не парсится из текста кнопки.
    """
    buttons = []
    for code in PLAN_ORDER:
        p        = PLANS[code]
        mark     = " ✓" if code == current_code else ""
        loc_word = "точка" if p["max_locations"] == 1 else "точек"
        price_rub = f"{p['price'] // 100:,}".replace(",", " ")
        label = (
            f"{p['name']} — до {p['max_locations']} {loc_word} — "
            f"{price_rub} ₽{mark}"
        )
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"pay_plan:{code}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def plan_action_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Продлить текущий тариф")],
        [KeyboardButton(text="Сменить тариф")],
        [KeyboardButton(text="Поддержка")],
        [KeyboardButton(text="Отмена")],
    ], resize_keyboard=True, one_time_keyboard=True)


# ── /subscription — раздел «Тариф и оплата» ─────────────────────────────────

@router.message(F.text.in_(["💳 Подписка", "Тариф"]))
@router.message(Command("subscription"))
async def billing_overview(message: Message):
    biz = await get_business_by_owner(message.from_user.id)
    if not biz:
        return
    sub  = await get_subscription(biz["id"])
    locs = await get_locations(biz["id"])
    plan = await get_business_plan(biz["id"])
    text = plan_summary_text(plan["code"], sub, len(locs))
    await message.answer(text, reply_markup=plan_action_kb())


# ── Продлить текущий тариф ───────────────────────────────────────────────────

@router.message(F.text == "Продлить текущий тариф")
@router.message(Command("pay"))
async def renew_plan(message: Message, bot: Bot):
    biz = await get_business_by_owner(message.from_user.id)
    if not biz:
        await message.answer("Сначала зарегистрируйте бизнес: /start")
        return
    plan = await get_business_plan(biz["id"])
    await create_plan_invoice(
        bot, message.chat.id, biz["id"],
        message.from_user.id, plan["code"]
    )


# ── Сменить тариф — показываем InlineKeyboard ────────────────────────────────

@router.message(F.text == "Сменить тариф")
@router.message(Command("change_plan"))
async def change_plan_start(message: Message):
    biz = await get_business_by_owner(message.from_user.id)
    if not biz:
        return
    plan = await get_business_plan(biz["id"])
    await message.answer(
        plan_list_text() + "\n\nВыберите тариф:",
        reply_markup=plan_inline_kb(plan["code"])
    )


# ── Обработка выбора тарифа через callback_data ──────────────────────────────

@router.callback_query(F.data.startswith("pay_plan:"))
async def plan_chosen_callback(callback: CallbackQuery, bot: Bot):
    """
    MED-4 FIX: plan_code приходит из callback_data="pay_plan:CODE",
    никакого парсинга русского текста.
    """
    plan_code = callback.data.split(":", 1)[1]   # "pay_plan:START" → "START"

    if plan_code not in PLAN_ORDER:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return

    biz = await get_business_by_owner(callback.from_user.id)
    if not biz:
        await callback.answer("Бизнес не найден.", show_alert=True)
        return

    current_plan = await get_business_plan(biz["id"])
    locs         = await get_locations(biz["id"])
    new_plan     = PLANS[plan_code]

    # Нельзя перейти на тариф с меньшим лимитом если точек больше
    if (new_plan["max_locations"] is not None
            and len(locs) > new_plan["max_locations"]):
        await callback.answer(
            f"Нельзя: у вас {len(locs)} точек, тариф «{new_plan['name']}» "
            f"допускает {new_plan['max_locations']}.",
            show_alert=True
        )
        return

    if plan_code == current_plan["code"]:
        await callback.answer(
            f"Вы уже на тарифе «{current_plan['name']}». "
            f"Для продления нажмите «Продлить текущий тариф».",
            show_alert=True
        )
        return

    # Создаём invoice
    await callback.answer()   # убираем часики
    await create_plan_invoice(
        bot, callback.message.chat.id, biz["id"],
        callback.from_user.id, plan_code
    )
