"""Определение роли и привязки пользователя к бизнесу."""
from typing import Callable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from database.models import get_business_by_owner, get_business_user
from config import config

class RoleMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Платформенный admin
        if user.id in config.ADMIN_IDS:
            data["role"] = "admin"
            data["business"] = None
            data["business_id"] = None
            return await handler(event, data)

        # Владелец?
        biz = await get_business_by_owner(user.id)
        if biz:
            data["role"] = "owner"
            data["business"] = biz
            data["business_id"] = biz["id"]
            return await handler(event, data)

        # Сотрудник / менеджер?
        bu = await get_business_user(user.id)
        if bu:
            data["role"] = bu["role"]
            data["business_user"] = bu
            data["business_id"] = bu["business_id"]
            return await handler(event, data)

        data["role"] = "new"
        data["business"] = None
        data["business_id"] = None
        return await handler(event, data)
