"""Системная админка v3 — поддержка, блокировки, статистика."""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import (
    get_all_businesses, get_sub_stats, get_month_payments,
    get_month_revenue, count_users, get_all_owner_ids,
    manual_activate_subscription, block_business,
    get_open_tickets, get_ticket, close_ticket, count_open_tickets
)
from config import config

router = Router()

class BroadcastState(StatesGroup):
    text = State()

def is_admin(tg_id: int) -> bool:
    return tg_id in config.ADMIN_IDS

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    users      = await count_users()
    businesses = await get_all_businesses()
    stats      = await get_sub_stats()
    revenue    = await get_month_revenue()
    payments   = await get_month_payments()
    tickets    = await count_open_tickets()
    await message.answer(
        f"🔧 ADMIN — BizPulse\n\n"
        f"Пользователей: {users}\n"
        f"Бизнесов: {len(businesses)}\n\n"
        f"Подписки:\n"
        f"  Trial:   {stats['trial']}\n"
        f"  Active:  {stats['active']}\n"
        f"  Expired: {stats['expired']}\n\n"
        f"Платежей за 30 дней: {len(payments)}\n"
        f"MRR: {revenue // 100} ₽\n\n"
        f"Открытых тикетов: {tickets}\n\n"
        f"Команды:\n"
        f"/admin_users — бизнесы\n"
        f"/admin_payments — платежи\n"
        f"/admin_tickets — заявки поддержки\n"
        f"/admin_close <id> <заметка> — закрыть тикет\n"
        f"/admin_activate <biz_id> — активировать подписку\n"
        f"/admin_block <biz_id> — заблокировать\n"
        f"/admin_unblock <biz_id> — разблокировать\n"
        f"/broadcast — рассылка"
    )

@router.message(Command("admin_users"))
async def admin_users(message: Message):
    if not is_admin(message.from_user.id):
        return
    businesses = await get_all_businesses()
    if not businesses:
        await message.answer("Бизнесов нет.")
        return
    lines = [
        f"{i+1}. {b['name']} (id:{b['id']}, owner:{b['owner_id']}"
        + (" 🚫" if b["is_blocked"] else "") + ")"
        for i, b in enumerate(businesses[:30])
    ]
    await message.answer("БИЗНЕСЫ\n\n" + "\n".join(lines))

@router.message(Command("admin_payments"))
async def admin_payments(message: Message):
    if not is_admin(message.from_user.id):
        return
    payments = await get_month_payments()
    if not payments:
        await message.answer("Платежей за 30 дней нет.")
        return
    lines = [
        f"• {p['paid_at'].strftime('%d.%m')} — {p['amount']//100} ₽ [{p['biz_name']}]"
        for p in payments
    ]
    total = sum(p["amount"] for p in payments)
    await message.answer(
        "ПЛАТЕЖИ\n\n" + "\n".join(lines) + f"\n\nИтого: {total//100} ₽"
    )

@router.message(Command("admin_tickets"))
async def admin_tickets(message: Message):
    if not is_admin(message.from_user.id):
        return
    tickets = await get_open_tickets()
    if not tickets:
        await message.answer("Открытых заявок нет.")
        return
    lines = []
    for t in tickets[:20]:
        lines.append(
            f"#{t['id']} [{t['status']}] {t['biz_name'] or '?'} "
            f"— {t['type']} · {t['created_at'].strftime('%d.%m %H:%M')}"
        )
    await message.answer(
        f"ЗАЯВКИ ({len(tickets)} открытых)\n\n" + "\n".join(lines)
        + "\n\nЗакрыть: /admin_close <id> <заметка>"
    )

@router.message(Command("admin_close"))
async def admin_close_ticket(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(None, 2)
    if len(parts) < 2:
        await message.answer("Использование: /admin_close <id> [заметка]")
        return
    try:
        ticket_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    note = parts[2] if len(parts) > 2 else ""
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await message.answer(f"Тикет #{ticket_id} не найден.")
        return
    await close_ticket(ticket_id, note)
    await message.answer(f"✅ Тикет #{ticket_id} закрыт.")

@router.message(Command("broadcast"))
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.text)
    await message.answer("Введите текст рассылки:")

@router.message(BroadcastState.text)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    text      = message.text.strip()
    owner_ids = await get_all_owner_ids()
    sent, failed = 0, 0
    for oid in owner_ids:
        try:
            await bot.send_message(oid, f"📢 Сообщение от BizPulse:\n\n{text}")
            sent += 1
        except Exception as e:
            logging.warning(f"Broadcast fail {oid}: {e}")
            failed += 1
    await message.answer(f"✅ Рассылка: отправлено {sent}, ошибок {failed}")

@router.message(Command("admin_activate"))
async def admin_activate(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /admin_activate <biz_id>")
        return
    try:
        bid = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    await manual_activate_subscription(bid)
    await message.answer(f"✅ Подписка для бизнеса {bid} активирована на 30 дней.")

@router.message(Command("admin_block"))
async def admin_block(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        return
    await block_business(int(parts[1]), True)
    await message.answer(f"🚫 Бизнес {parts[1]} заблокирован.")

@router.message(Command("admin_unblock"))
async def admin_unblock(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        return
    await block_business(int(parts[1]), False)
    await message.answer(f"✅ Бизнес {parts[1]} разблокирован.")

@router.message(Command("admin_set_plan"))
async def admin_set_plan(message: Message):
    """Вручную сменить тариф: /admin_set_plan <biz_id> <plan_code>"""
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Использование: /admin_set_plan <biz_id> START|GROW|NETWORK")
        return
    try:
        bid  = int(parts[1])
        code = parts[2].upper()
    except ValueError:
        await message.answer("Неверный формат.")
        return
    from services.plan_service import PLAN_ORDER, set_business_plan
    if code not in PLAN_ORDER:
        await message.answer(f"Тариф {code} не существует.")
        return
    await set_business_plan(bid, code)
    await message.answer(f"✅ Тариф бизнеса {bid} изменён на {code}.")

@router.message(Command("admin_extend"))
async def admin_extend(message: Message):
    """Продлить подписку: /admin_extend <biz_id> [days=30]"""
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /admin_extend <biz_id> [дней=30]")
        return
    try:
        bid  = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else 30
    except ValueError:
        await message.answer("Неверный формат.")
        return
    from database.models import manual_activate_subscription
    await manual_activate_subscription(bid, days)
    await message.answer(f"✅ Подписка бизнеса {bid} продлена на {days} дней.")

@router.message(Command("admin_plans"))
async def admin_plans(message: Message):
    """Обзор бизнесов с тарифами."""
    if not is_admin(message.from_user.id):
        return
    pool = __import__("database.session", fromlist=["get_pool"]).get_pool()
    rows = await pool.fetch(
        """SELECT b.id, b.name, s.plan_code, s.status,
                  s.current_period_end, s.trial_ends_at,
                  COUNT(l.id) as loc_count
           FROM businesses b
           LEFT JOIN subscriptions s ON s.business_id=b.id
           LEFT JOIN locations l ON l.business_id=b.id AND l.is_active=TRUE
           GROUP BY b.id, b.name, s.plan_code, s.status,
                    s.current_period_end, s.trial_ends_at
           ORDER BY b.created_at DESC LIMIT 25"""
    )
    if not rows:
        await message.answer("Нет бизнесов.")
        return
    lines = ["БИЗНЕСЫ / ТАРИФЫ\n"]
    for r in rows:
        ends = r["current_period_end"] or r["trial_ends_at"]
        ends_str = ends.strftime("%d.%m") if ends else "?"
        lines.append(
            f"#{r['id']} {r['name']} · {r['plan_code'] or 'START'} · "
            f"{r['status'] or '?'} · до {ends_str} · {r['loc_count']} точек"
        )
    lines.append("\n/admin_set_plan <id> <план> — сменить тариф")
    lines.append("/admin_extend <id> [дней] — продлить")
    await message.answer("\n".join(lines))


# ── ЗАГЛУШКИ ДЛЯ КНОПОК ADMIN-МЕНЮ ─────────────────────────────────────────

@router.message(F.text == "📊 Статистика")
async def admin_stats_btn(message: Message):
    if not is_admin(message.from_user.id):
        return
    # Перенаправляем на /admin
    await admin_panel(message)

@router.message(F.text == "🏢 Бизнесы")
async def admin_businesses_btn(message: Message):
    if not is_admin(message.from_user.id):
        return
    await admin_users(message)

@router.message(F.text == "💳 Платежи")
async def admin_payments_btn(message: Message):
    if not is_admin(message.from_user.id):
        return
    await admin_payments(message)

@router.message(F.text == "📢 Рассылка")
async def admin_broadcast_btn(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await broadcast_start(message, state)

@router.message(F.text == "✅ Активировать")
async def admin_activate_btn(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Чтобы активировать подписку, используйте команду:\n"
        "/admin_activate <business_id>\n\n"
        "Список бизнесов: /admin_users"
    )

@router.message(F.text == "🚫 Заблокировать")
async def admin_block_btn(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Чтобы заблокировать бизнес, используйте команду:\n"
        "/admin_block <business_id>\n\n"
        "Чтобы разблокировать:\n"
        "/admin_unblock <business_id>\n\n"
        "Список бизнесов: /admin_users"
    )
