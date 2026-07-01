"""Сервис оплаты v3 — мультитарифный invoice, идемпотентность."""
import uuid
import logging
from aiogram import Bot
from aiogram.types import LabeledPrice
from database.models import (
    create_payment, get_payment_by_internal_id,
    confirm_payment, activate_subscription,
    get_subscription, get_business
)
from services.plan_service import PLANS, set_business_plan
from config import config

async def create_plan_invoice(bot: Bot, chat_id: int,
                              business_id: int, user_id: int,
                              plan_code: str) -> bool:
    """Создать invoice для выбранного тарифа."""
    if not config.PAYMENT_PROVIDER_TOKEN:
        await bot.send_message(
            chat_id,
            "⚠️ Платёжный провайдер не настроен.\n"
            f"Обратитесь в поддержку: {config.SUPPORT_USERNAME}"
        )
        return False

    plan = PLANS.get(plan_code)
    if not plan:
        await bot.send_message(chat_id, "Тариф не найден.")
        return False

    if plan_code not in ("START", "GROW", "NETWORK") or plan["price"] == 0:
        await bot.send_message(
            chat_id,
            "Этот тариф сейчас недоступен для оплаты.\n\n"
            f"Напишите в поддержку: {config.SUPPORT_USERNAME}"
        )
        return False

    internal_id = str(uuid.uuid4())
    await create_payment(
        business_id, user_id, "telegram_payments",
        plan["price"], internal_id, plan_code
    )

    sub = await get_subscription(business_id)
    is_renewal = (sub and sub.get("plan_code") == plan_code
                  and sub["status"] == "active")
    label = f"{'Продление' if is_renewal else 'Подписка'} «{plan['name']}» — 30 дней"

    # Payload: sub_{business_id}_{internal_id}_{plan_code}
    payload = f"sub_{business_id}_{internal_id}_{plan_code}"

    offer_line = f"\n\nОферта: {config.OFFER_URL}" if config.OFFER_URL else ""

    await bot.send_invoice(
        chat_id=chat_id,
        title=f"BizPulse — {plan['name']}",
        description=(
            f"• До {plan['max_locations']} точек\n"
            f"• Все функции BizPulse\n"
            f"• ИИ-аналитика каждый день"
            + offer_line
        ),
        payload=payload,
        provider_token=config.PAYMENT_PROVIDER_TOKEN,
        currency=config.PAYMENT_CURRENCY,
        prices=[LabeledPrice(label=label, amount=plan["price"])],
    )
    return True

async def handle_successful_payment(payload: str, tg_charge_id: str,
                                     provider_charge_id: str = "",
                                     user_id: int = None,
                                     raw: dict = None) -> dict:
    """
    Разбирает payload: sub_{business_id}_{internal_id}_{plan_code}
    Возвращает {ok, business_id, plan_code, duplicate, error}
    """
    try:
        # поддерживаем старый формат sub_{bid}_{uuid} и новый sub_{bid}_{uuid}_{plan}
        parts = payload.split("_", 3)
        if len(parts) < 3 or parts[0] != "sub":
            return {"ok": False, "error": f"Неверный payload: {payload}"}
        business_id = int(parts[1])
        internal_id = parts[2]
        plan_code   = parts[3] if len(parts) == 4 else "START"
    except (ValueError, IndexError) as e:
        return {"ok": False, "error": str(e)}

    # Идемпотентность
    payment = await get_payment_by_internal_id(internal_id)
    if not payment:
        logging.error(f"Payment not found: {internal_id}")
        return {"ok": False, "error": "Платёж не найден в системе"}

    if payment["status"] == "paid":
        logging.warning(f"Duplicate payment: {internal_id}")
        return {"ok": True, "business_id": business_id,
                "plan_code": plan_code, "duplicate": True}

    await confirm_payment(internal_id, tg_charge_id, provider_charge_id, raw)
    await activate_subscription(business_id)
    await set_business_plan(business_id, plan_code)

    logging.info(
        f"Payment OK: business={business_id}, plan={plan_code}, "
        f"internal={internal_id}, charge={tg_charge_id}"
    )
    return {
        "ok": True, "business_id": business_id,
        "plan_code": plan_code, "duplicate": False
    }

async def validate_pre_checkout(payload: str, amount: int,
                                  currency: str, user_id: int) -> dict:
    """
    Валидация перед оплатой (pre_checkout_query).
    Возвращает {ok: bool, error: str}
    """
    try:
        parts = payload.split("_", 3)
        if len(parts) < 3 or parts[0] != "sub":
            return {"ok": False, "error": "Неверный формат заказа."}
        business_id = int(parts[1])
        plan_code   = parts[3] if len(parts) == 4 else "START"
    except (ValueError, IndexError):
        return {"ok": False, "error": "Ошибка данных заказа."}

    # Проверяем тариф
    plan = PLANS.get(plan_code)
    if not plan or plan["price"] == 0:
        return {"ok": False, "error": f"Тариф {plan_code} не найден."}

    # Сумма совпадает
    if amount != plan["price"]:
        return {
            "ok": False,
            "error": f"Неверная сумма. Ожидалось {plan['price'] // 100} ₽, получено {amount // 100} ₽."
        }

    # Валюта
    if currency != config.PAYMENT_CURRENCY:
        return {"ok": False, "error": "Неверная валюта."}

    # Проверяем что user — owner бизнеса
    from database.models import get_business
    biz = await get_business(business_id)
    if not biz or biz["owner_id"] != user_id:
        return {"ok": False, "error": "Нет прав для оплаты этого бизнеса."}

    return {"ok": True}
