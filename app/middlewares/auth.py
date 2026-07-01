"""Rate limit и базовая идентификация."""
import time
from typing import Callable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from database.models import upsert_user

_rate: dict = {}
RATE_LIMIT   = 1.0    # секунд между сообщениями
_RATE_MAX    = 10_000 # максимальный размер кэша перед очисткой

class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        # Rate limit
        now = time.time()
        last = _rate.get(user.id, 0)
        if now - last < RATE_LIMIT:
            return  # молча игнорируем спам
        _rate[user.id] = now
        # HIGH-3 FIX: очищаем устаревшие записи при превышении лимита
        if len(_rate) > _RATE_MAX:
            cutoff = now - RATE_LIMIT * 100
            for k in [k for k, v in _rate.items() if v < cutoff]:
                del _rate[k]
        # Upsert user
        await upsert_user(user.id, user.full_name or "", user.username or "")
        return await handler(event, data)
