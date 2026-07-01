"""Проверка подписки v3 — trial один раз на пользователя."""
from datetime import timezone
from database.models import get_subscription, expire_subscription, has_used_trial
from utils.dates import now_utc

async def check_subscription_status(business_id: int) -> str:
    sub = await get_subscription(business_id)
    if not sub:
        return "expired"
    now    = now_utc()
    status = sub["status"]
    if status == "trial":
        ends = sub["trial_ends_at"]
        if ends and now > ends.replace(tzinfo=timezone.utc):
            await expire_subscription(business_id)
            return "expired"
    elif status == "active":
        ends = sub["current_period_end"]
        if ends and now > ends.replace(tzinfo=timezone.utc):
            await expire_subscription(business_id)
            return "expired"
    return status

def subscription_status_text(sub) -> str:
    if not sub:
        return "❌ Нет подписки"
    status = sub["status"]
    if status == "trial":
        ends = sub["trial_ends_at"]
        date_str = ends.strftime("%d.%m.%Y") if ends else "?"
        return f"🎁 Пробный период до {date_str}"
    if status == "active":
        ends = sub["current_period_end"]
        date_str = ends.strftime("%d.%m.%Y") if ends else "?"
        return f"✅ Активна до {date_str}"
    if status == "expired":
        return "❌ Истекла — /pay"
    if status == "canceled":
        return "🚫 Отменена"
    return status

async def can_start_trial(tg_id: int) -> bool:
    """Проверить, может ли пользователь начать trial."""
    return not await has_used_trial(tg_id)
