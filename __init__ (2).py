"""Telegram Payments v3 — мультитарифный, с валидацией pre_checkout."""
from aiogram import Router, F
from aiogram.types import Message, PreCheckoutQuery
from database.models import get_business_by_owner, get_subscription, get_locations
from services.payment_service import (
    handle_successful_payment, validate_pre_checkout
)
from services.plan_service import PLANS, plan_summary_text, get_business_plan
from services.notification_service import notify_admins, msg_payment_received
from services.subscription_service import subscription_status_text
from config import config

router = Router()

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    result = await validate_pre_checkout(
        payload=query.invoice_payload,
        amount=query.total_amount,
        currency=query.currency,
        user_id=query.from_user.id,
    )
    if result["ok"]:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message=result["error"])

@router.message(F.successful_payment)
async def successful_payment(message: Message, bot=None):
    payment = message.successful_payment
    biz     = await get_business_by_owner(message.from_user.id)
    if not biz:
        return

    result = await handle_successful_payment(
        payload=payment.invoice_payload,
        tg_charge_id=payment.telegram_payment_charge_id,
        provider_charge_id=getattr(payment, "provider_payment_charge_id", ""),
        user_id=message.from_user.id,
        raw={
            "total_amount": payment.total_amount,
            "currency":     payment.currency,
            "charge_id":    payment.telegram_payment_charge_id,
        }
    )

    if result.get("duplicate"):
        await message.answer("Эта оплата уже была обработана ранее.")
        return

    if result.get("ok"):
        sub      = await get_subscription(biz["id"])
        locs     = await get_locations(biz["id"])
        plan     = await get_business_plan(biz["id"])
        plan_obj = PLANS.get(result.get("plan_code", "START"), PLANS["START"])
        await message.answer(
            f"✅ Оплата прошла успешно!\n\n"
            f"Тариф: {plan_obj['name']}\n"
            f"Статус: {subscription_status_text(sub)}\n\n"
            f"/subscription — подробнее"
        )
        if bot:
            await notify_admins(
                bot,
                msg_payment_received(biz["name"], payment.total_amount)
                + f"\nТариф: {plan_obj['name']}"
            )
    else:
        await message.answer(
            f"⚠️ Оплата получена, но произошла ошибка активации.\n"
            f"Обратитесь в поддержку: {config.SUPPORT_USERNAME}\n"
            f"Ошибка: {result.get('error','?')}"
        )
