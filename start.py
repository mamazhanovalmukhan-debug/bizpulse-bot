"""Онбординг v6 — стабильная регистрация, state.clear() только после успеха."""
import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import (
    create_business, create_location, create_subscription,
    add_business_user, create_trial_usage, has_used_trial
)
from services.notification_service import notify_admins, msg_new_business
from services.plan_service import set_business_plan
from utils.dates import TIMEZONES
from utils.formatting import CATEGORY_NAMES

router = Router()
log    = logging.getLogger("onboarding")

CATEGORY_MAP = {
    "Кофейня": "coffee_shop", "Шаурма": "shawarma",
    "Табачный магазин": "tobacco", "Пекарня": "bakery",
    "Магазин": "retail", "Другое": "other",
}
TZ_MAP = {label: tz for tz, label in TIMEZONES}

def plan_for_locations(count: int) -> str:
    """Подобрать тариф по количеству точек при онбординге."""
    if count <= 1:
        return "START"
    if count <= 5:
        return "GROW"
    return "NETWORK"


class OnboardingState(StatesGroup):
    biz_name     = State()
    biz_category = State()
    city         = State()
    biz_timezone = State()
    loc_count    = State()
    loc_name     = State()
    loc_address  = State()
    loc_open     = State()
    loc_close    = State()


def kb_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )

def kb_skip_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить"),
                   KeyboardButton(text="Отмена")]],
        resize_keyboard=True, one_time_keyboard=True
    )


async def start_onboarding(message: Message, state: FSMContext, bot=None):
    from config import config
    tg_id = message.from_user.id
    used  = await has_used_trial(tg_id)

    if used:
        trial_note = "\n\n⚠️ Бесплатный период уже был использован. Для нового бизнеса потребуется оплата."
    else:
        trial_note = f"\n\n🎁 Первые {config.DEFAULT_TRIAL_DAYS} дней бесплатно."

    await state.clear()
    await state.set_state(OnboardingState.biz_name)
    await message.answer(
        "BizPulse — цифровой управляющий для вашего бизнеса.\n\n"
        "Он помогает контролировать:\n"
        "— смены и сотрудников\n"
        "— выручку и кассу\n"
        "— расходы и возвраты\n"
        "— поставки и остатки\n"
        "— проблемы и отклонения\n\n"
        "Вы получаете аналитику в Telegram — без таблиц и лишних чатов."
        + trial_note + "\n\n"
        "Как называется ваш бизнес?",
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(OnboardingState.biz_name)
async def step_biz_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Введите название (минимум 2 символа):")
        return
    await state.update_data(biz_name=name)
    await state.set_state(OnboardingState.biz_category)
    await message.answer(
        f"Бизнес: {name} ✓\n\nКакая сфера?",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Кофейня"), KeyboardButton(text="Шаурма")],
            [KeyboardButton(text="Табачный магазин"), KeyboardButton(text="Пекарня")],
            [KeyboardButton(text="Магазин"), KeyboardButton(text="Другое")],
        ], resize_keyboard=True, one_time_keyboard=True)
    )


@router.message(OnboardingState.biz_category)
async def step_category(message: Message, state: FSMContext):
    cat = CATEGORY_MAP.get(message.text)
    if not cat:
        await message.answer("Выберите сферу из списка:")
        return
    await state.update_data(biz_category=cat)
    await state.set_state(OnboardingState.city)
    await message.answer(
        "Город?\nНапример: Москва, Казань, Краснодар:",
        reply_markup=kb_cancel()
    )


@router.message(OnboardingState.city)
async def step_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(OnboardingState.biz_timezone)
    await message.answer(
        "Часовой пояс?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=label)] for _, label in TIMEZONES],
            resize_keyboard=True, one_time_keyboard=True
        )
    )


@router.message(OnboardingState.biz_timezone)
async def step_timezone(message: Message, state: FSMContext):
    tz = TZ_MAP.get(message.text)
    if not tz:
        await message.answer("Выберите часовой пояс из списка:")
        return
    await state.update_data(biz_timezone=tz, locations=[], current_loc=1)
    await state.set_state(OnboardingState.loc_count)
    await message.answer(
        "Сколько торговых точек? (от 1 до 15):\n\n"
        "Тариф на пробный период подберётся автоматически:\n"
        "1 точка — Старт, до 5 — Рост, до 15 — Сеть."
    )


@router.message(OnboardingState.loc_count)
async def step_loc_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if not 1 <= count <= 15:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 15:")
        return
    await state.update_data(loc_count=count, current_loc=1, locations=[])
    await state.set_state(OnboardingState.loc_name)
    await message.answer(
        f"Название точки 1 из {count}:\nНапример: Центральная, ТЦ Мега:"
    )


@router.message(OnboardingState.loc_name)
async def step_loc_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Название слишком короткое:")
        return
    data = await state.get_data()
    locs = data.get("locations", [])
    locs.append({"name": name})
    await state.update_data(locations=locs)
    await state.set_state(OnboardingState.loc_address)
    await message.answer(
        f"Адрес точки «{name}»?\nЕсли не нужно — Пропустить:",
        reply_markup=kb_skip_cancel()
    )


@router.message(OnboardingState.loc_address)
async def step_loc_address(message: Message, state: FSMContext):
    address = "" if message.text == "Пропустить" else message.text.strip()
    data = await state.get_data()
    locs = data.get("locations", [])
    locs[-1]["address"] = address
    await state.update_data(locations=locs)
    await state.set_state(OnboardingState.loc_open)
    await message.answer(
        "Время открытия точки (час, например: 8 или 9):",
        reply_markup=kb_cancel()
    )


@router.message(OnboardingState.loc_open)
async def step_loc_open(message: Message, state: FSMContext):
    try:
        h = int(message.text.strip())
        if not 0 <= h <= 23:
            raise ValueError
    except ValueError:
        await message.answer("Введите час от 0 до 23:")
        return
    data = await state.get_data()
    locs = data.get("locations", [])
    locs[-1]["open_time"] = h
    await state.update_data(locations=locs)
    await state.set_state(OnboardingState.loc_close)
    await message.answer(f"Открытие: {h}:00 ✓\n\nВремя закрытия?")


@router.message(OnboardingState.loc_close)
async def step_loc_close(message: Message, state: FSMContext, bot=None):
    try:
        h = int(message.text.strip())
        if not 0 <= h <= 23:
            raise ValueError
    except ValueError:
        await message.answer("Введите час от 0 до 23:")
        return

    data    = await state.get_data()
    locs    = data.get("locations", [])
    locs[-1]["close_time"] = h
    current = data.get("current_loc", 1)
    total   = data.get("loc_count", 1)
    await state.update_data(locations=locs, current_loc=current + 1)

    if current < total:
        await state.set_state(OnboardingState.loc_name)
        await message.answer(
            f"Точка {current} добавлена ✓\n\n"
            f"Название точки {current+1} из {total}:"
        )
        return

    # ── Финал: сначала все операции с БД, потом state.clear() ──────────────
    user = message.from_user
    from config import config

    try:
        tz     = data["biz_timezone"]
        biz_id = await create_business(
            user.id, data["biz_name"], data["biz_category"], tz,
            data.get("city", "")
        )
        await add_business_user(biz_id, user.id, "owner")

        for loc in locs:
            await create_location(
                biz_id, loc["name"], loc.get("address", ""),
                loc.get("open_time", 9), loc.get("close_time", 21), tz
            )

        # Trial — только если пользователь ещё не использовал.
        # Тариф выбираем по количеству точек, чтобы trial не создавал
        # бизнес на 2–15 точек внутри тарифа START с лимитом 1.
        plan_code = plan_for_locations(total)
        used = await has_used_trial(user.id)
        if not used:
            await create_subscription(biz_id, config.DEFAULT_TRIAL_DAYS)
            await create_trial_usage(user.id, biz_id, config.DEFAULT_TRIAL_DAYS)
            await set_business_plan(biz_id, plan_code)
            sub_text = (
                f"🎁 Бесплатный период: {config.DEFAULT_TRIAL_DAYS} дней\n"
                f"Тариф на пробный период: {plan_code}"
            )
        else:
            # Trial уже использован — создаём expired подписку, нужна оплата
            from database.session import get_pool
            await get_pool().execute(
                """INSERT INTO subscriptions (business_id, status)
                   VALUES ($1, 'expired')
                   ON CONFLICT (business_id) DO NOTHING""",
                biz_id
            )
            await set_business_plan(biz_id, plan_code)
            sub_text = "⚠️ Бесплатный период уже использован. Оплатите: /pay"

        # FSM очищаем только после успеха всех операций
        await state.clear()

        locs_text = "\n".join(
            f"• {l['name']} ({l.get('open_time', 9)}:00–{l['close_time']}:00)"
            for l in locs
        )

        from keyboards.owner import owner_main_kb
        await message.answer(
            f"🎉 Бизнес зарегистрирован!\n\n"
            f"Компания: {data['biz_name']}\n"
            f"Город: {data.get('city', '')}\n\n"
            f"Точки:\n{locs_text}\n\n"
            f"{sub_text}\n\n"
            f"Следующий шаг — пригласите сотрудников:\n"
            f"/invite_employee",
            reply_markup=owner_main_kb()
        )

        # Уведомляем админов
        if bot:
            await notify_admins(
                bot,
                msg_new_business(data["biz_name"], user.full_name or "")
            )

    except Exception as e:
        log.error(f"Onboarding final step error for user {user.id}: {e}", exc_info=True)
        # Не очищаем state — пользователь может попробовать ещё раз
        await message.answer(
            "⚠️ Произошла ошибка при создании бизнеса.\n\n"
            "Попробуйте снова через несколько секунд или напишите /start.\n"
            f"Если ошибка повторяется — обратитесь в поддержку: {config.SUPPORT_USERNAME}"
        )
