"""Уведомления v3 — расширенные типы."""
import logging
from aiogram import Bot
from config import config

async def notify(bot: Bot, chat_id: int, text: str, silent: bool = False):
    try:
        await bot.send_message(chat_id=chat_id, text=text,
                               disable_notification=silent)
    except Exception as e:
        logging.warning(f"Notify failed {chat_id}: {e}")

async def notify_owner(bot: Bot, owner_id: int, text: str):
    await notify(bot, owner_id, text)

async def notify_admins(bot: Bot, text: str):
    for admin_id in config.ADMIN_IDS:
        await notify(bot, admin_id, text, silent=True)

async def notify_location_employees(bot: Bot, location_id: int, text: str):
    from database.models import get_location_employees
    for u in await get_location_employees(location_id):
        await notify(bot, u["user_id"], text, silent=True)

async def notify_business_employees(bot: Bot, business_id: int, text: str):
    from database.models import get_business_users
    for u in await get_business_users(business_id):
        if u["role"] in ("employee", "manager"):
            await notify(bot, u["user_id"], text, silent=True)

# ── Шаблоны ─────────────────────────────────────────────────────────────────

def msg_shift_not_opened(loc: str) -> str:
    return f"⚠️ Точка «{loc}» — прошёл час, смена не открыта!"

def msg_opening_reminder(loc: str) -> str:
    return f"☀️ Доброе утро! Не забудьте открыть смену.\n\nТочка: {loc}"

def msg_closing_reminder(loc: str) -> str:
    return f"🌙 Скоро конец рабочего дня.\n\nТочка: {loc}\n\nЗакройте смену."

def msg_sub_expiring(days: int, biz_name: str) -> str:
    d = "день" if days == 1 else "дня"
    return (
        f"⏰ Подписка BizPulse истекает через {days} {d}!\n\n"
        f"Бизнес: {biz_name}\n\nОплатите: /pay"
    )

def msg_sub_expired(biz_name: str) -> str:
    return (
        f"🔒 Подписка закончилась.\n\n"
        f"Бизнес: {biz_name}\n\n"
        f"Оплатите следующий месяц: /pay\n"
        f"Поддержка: {config.SUPPORT_USERNAME}"
    )

def msg_new_business(biz_name: str, owner_name: str) -> str:
    return f"🆕 Новый бизнес: {biz_name}\nВладелец: {owner_name}"

def msg_payment_received(biz_name: str, amount: int) -> str:
    return f"💳 Оплата: {biz_name} — {amount // 100} ₽"

def msg_stock_alert(product_name: str, current: float,
                     minimum: float, unit: str) -> str:
    return (
        f"📦 Товар заканчивается!\n\n"
        f"{product_name}: {current} {unit} (мин. {minimum} {unit})\n"
        f"Оформите заказ у поставщика."
    )

def msg_delivery_received(supplier_name: str, location_name: str,
                           has_discrepancy: bool) -> str:
    status = "с расхождениями ⚠️" if has_discrepancy else "без замечаний ✅"
    return (
        f"📦 Поставка принята {status}\n\n"
        f"Поставщик: {supplier_name}\n"
        f"Точка: {location_name}"
    )

def msg_support_ticket(ticket_id: int, biz_name: str, role: str,
                        ttype: str, message: str) -> str:
    return (
        f"🆘 Новая заявка #{ticket_id}\n\n"
        f"Бизнес: {biz_name}\nРоль: {role}\nТип: {ttype}\n\n"
        f"{message[:300]}"
    )
