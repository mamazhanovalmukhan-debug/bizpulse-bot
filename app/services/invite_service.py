"""Генерация и обработка invite-ссылок для сотрудников."""
import secrets
from datetime import timezone, timedelta
from database.models import create_invite, get_invite, use_invite, add_business_user, upsert_user
from utils.dates import now_utc

async def generate_invite(business_id: int, location_id: int, role: str,
                           bot_username: str) -> str:
    token     = secrets.token_urlsafe(16)
    expires   = now_utc() + timedelta(days=7)
    await create_invite(business_id, location_id, role, token, expires)
    return f"https://t.me/{bot_username}?start=invite_{token}"

async def handle_invite(token: str, tg_id: int, full_name: str,
                        username: str = "") -> dict:
    """Обработать переход по invite-ссылке. Возвращает результат."""
    invite = await get_invite(token)
    if not invite:
        return {"ok": False, "reason": "Ссылка недействительна."}
    if invite["is_used"]:
        return {"ok": False, "reason": "Эта ссылка уже была использована."}
    if invite["expires_at"] and invite["expires_at"].replace(tzinfo=timezone.utc) < now_utc():
        return {"ok": False, "reason": "Ссылка устарела. Попросите владельца выслать новую."}
    await upsert_user(tg_id, full_name, username)
    await add_business_user(invite["business_id"], tg_id, invite["role"], invite["location_id"])
    await use_invite(token, tg_id)
    return {
        "ok": True,
        "business_id": invite["business_id"],
        "location_id": invite["location_id"],
        "role": invite["role"],
    }
