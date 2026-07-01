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
            if isinstance(event, Message):
                await event.answer(msg)
            elif isinstance(event, CallbackQuery):
                await event.answer("Подписка истекла.", show_alert=True)
            return

        return await handler(event, data)
