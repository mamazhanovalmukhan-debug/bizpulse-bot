"""Демо-данные — только для ADMIN в DEBUG-режиме."""
import logging
from datetime import datetime, timedelta, timezone, date
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from database.models import (
    get_business_by_owner, get_locations,
    open_shift, close_shift_db,
    add_movement, add_shift_note, save_cash_check, save_ai_report
)
from config import config

router = Router()

@router.message(Command("demo_data"))
async def cmd_demo_data(message: Message):
    # Только admin И только в DEBUG
    if message.from_user.id not in config.ADMIN_IDS:
        return
    if not config.DEBUG:
        await message.answer("demo_data доступно только в режиме DEBUG=true")
        return

    biz = await get_business_by_owner(message.from_user.id)
    if not biz:
        await message.answer("Сначала зарегистрируйте бизнес: /start")
        return
    locs = await get_locations(biz["id"])
    if not locs:
        await message.answer("Нет активных точек.")
        return

    await message.answer("⏳ Создаю демо-данные за 6 дней...")

    import random
    random.seed(42)

    loc    = locs[0]
    biz_id = biz["id"]
    loc_id = loc["id"]
    uid    = message.from_user.id

    from database.session import get_pool

    for day_offset in range(6, 0, -1):
        shift_date = date.today() - timedelta(days=day_offset)
        cash_sales = random.randint(4000, 10000)
        card_sales = random.randint(2000,  7000)
        agg_sales  = random.randint(500,   3000)
        expenses   = random.choice([0, 0, 400, 700])
        opening    = random.randint(4000, 6000)
        try:
            shift_id = await open_shift(biz_id, loc_id, uid, float(opening), "Демо")
            await get_pool().execute(
                "UPDATE shifts SET date=$2, opened_at=$3 WHERE id=$1",
                shift_id, shift_date,
                datetime(shift_date.year, shift_date.month, shift_date.day,
                         9, 0, tzinfo=timezone.utc)
            )
            await add_movement(biz_id, loc_id, shift_id, "sale_cash", cash_sales, "", uid)
            await add_movement(biz_id, loc_id, shift_id, "sale_card", card_sales, "", uid)
            await add_movement(biz_id, loc_id, shift_id, "sale_sbp",  agg_sales,  "", uid)
            if expenses > 0:
                await add_movement(biz_id, loc_id, shift_id, "expense",
                                   expenses, "Расходные материалы", uid)
            expected = opening + cash_sales - expenses
            actual   = expected - 500 if day_offset == 3 else expected
            diff     = actual - expected
            status   = "shortage" if diff < 0 else "ok"
            await save_cash_check(biz_id, loc_id, shift_id, expected, actual, diff, status, uid)
            notes = ["Закончились круассаны в 17:00",
                     "Всё хорошо", "Нужно заказать молоко",
                     "Много туристов", "Поставка стаканов", "Нет замечаний"]
            await add_shift_note(biz_id, loc_id, shift_id, uid,
                                  notes[day_offset % len(notes)], day_offset % 2 == 0)
            await close_shift_db(shift_id, uid, float(actual), "Демо-закрытие")
            await get_pool().execute(
                "UPDATE shifts SET closed_at=$2 WHERE id=$1",
                shift_id,
                datetime(shift_date.year, shift_date.month, shift_date.day,
                         21, 0, tzinfo=timezone.utc)
            )
        except Exception as e:
            logging.error(f"Demo error day {day_offset}: {e}")

    await save_ai_report(biz_id, "daily",
        "📊 Демо-анализ\n\n"
        "💡 Обнаружена недостача 500 ₽ на 3-й день.\n"
        "💸 В 17:00 закончились круассаны — возможная потеря 10-15% выручки.\n"
        "✅ Протестируйте увеличение остатка выпечки на вечер.\n"
        "⚠️ Это демо-данные. Реальный анализ появится после 3-5 рабочих дней."
    )

    await message.answer(
        "✅ Демо-данные созданы!\n\n"
        "• 6 смен за 6 дней\n"
        "• Продажи: нал, безнал, агрегаторы\n"
        "• Расходы\n"
        "• Недостача 500 ₽ на 3-й день\n"
        "• Заметки сотрудников\n"
        "• ИИ-отчёт\n\n"
        "Попробуйте: /today · /week · /status"
    )
