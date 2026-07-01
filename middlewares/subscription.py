"""Middleware подписки v3 — блокирует owner + сотрудников."""
from typing import Callable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from services.subscription_service import check_subscription_status
from config import config

EXEMPT = {
    "/pay", "/subscription", "/help", "/legal", "/support",
    "/start", "/myid", "/change_plan", "/billing",
    "💳 Подписка", "🆘 Поддержка", "🆘 Помощь",
    "Тариф", "Сменить тариф", "Продлить текущий тариф",
    "Поддержка",
}

# Callback data префиксы, разрешённые при expired подписке
EXEMPT_CALLBACK_PREFIXES = (
    "pay_plan:",  # выбор тарифа в billing
)

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable,
                       event: TelegramObject, data: dict) -> Any:
        user = data.get("event_from_user")
        if not user or user.id in config.ADMIN_IDS:
            return await handler(event, data)

        role        = data.get("role", "new")
        business_id = data.get("business_id")

        if role == "new" or not business_id:
            return await handler(event, data)

        status = await check_subscription_status(business_id)
        data["sub_status"] = status

        if status in ("expired", "canceled"):
            # CallbackQuery — проверяем callback_data префиксы
            if isinstance(event, CallbackQuery):
                cdata = event.data or ""
                if any(cdata.startswith(p) for p in EXEMPT_CALLBACK_PREFIXES):
                    return await handler(event, data)
                await event.answer("Подписка истекла. Оплатите: /pay", show_alert=True)
                return

            text = ""
            if isinstance(event, Message) and event.text:
                text = event.text

            for exempt in EXEMPT:
                if text.startswith(exempt) or text == exempt:
                    return await handler(event, data)

            # Блокируем — и owner, и сотрудников
            msg = (
                "🔒 Подписка закончилась.\n\n"
                "Для продолжения работы оплатите следующий месяц: /pay\n"
                "Сменить тариф: /change_plan\n"
                f"Поддержка: {config.SUPPORT_USERNAME}"
            )
            await event.answer(msg)
            return

        return await handler(event, data)
