"""Единый обработчик ошибок — перехватывает все исключения."""
import logging
import traceback
from typing import Callable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import config

log = logging.getLogger("error_handler")

FRIENDLY_MSG = (
    "⚠️ Произошла техническая ошибка.\n\n"
    "Мы уже разбираемся с проблемой.\n"
    f"Если ошибка повторяется — напишите в поддержку: {config.SUPPORT_USERNAME}"
)

class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable,
                       event: TelegramObject, data: dict) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            tb = traceback.format_exc()
            log.error(f"Unhandled exception: {exc}\n{tb}")

            # Уведомить администраторов
            bot = data.get("bot")
            user = data.get("event_from_user")
            if bot:
                short = str(exc)[:200]
                uid   = user.id if user else "?"
                for admin_id in config.ADMIN_IDS:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"🚨 ОШИБКА БОТА\n\n"
                            f"Пользователь: {uid}\n"
                            f"Ошибка: {short}\n\n"
                            f"{tb[-800:]}"
                        )
                    except Exception as notify_err:
                        log.warning(f"Admin notify failed: {notify_err}")

            # Показать дружелюбное сообщение
            try:
                if isinstance(event, Message):
                    await event.answer(FRIENDLY_MSG)
                elif isinstance(event, CallbackQuery):
                    await event.answer("Произошла ошибка.", show_alert=True)
                    await event.message.answer(FRIENDLY_MSG)
            except Exception as reply_err:
                log.warning(f"User reply failed: {reply_err}")
