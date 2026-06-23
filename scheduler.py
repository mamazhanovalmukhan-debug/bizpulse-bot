import logging
from datetime import datetime, date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from config import OWNER_ID, EMPLOYEE_POINTS, OPENING_HOUR_UTC, CLOSING_HOUR_UTC, DIGEST_HOUR_UTC, MSK
from storage import get_today_summary, get_today_reports, get_week_reports, get_yesterday_closing
from ai_analyst import analyze_day, weekly_advice

scheduler = AsyncIOScheduler()

def fmt(x): return f"{x:,.0f} р".replace(",", " ")

async def send_opening_reminder(bot: Bot):
    for user_id, point in EMPLOYEE_POINTS.items():
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"Доброе утро!\n\nТочка: {point}\n\nНажми Открытие смены чтобы начать день.",
            )
        except Exception as e:
            logging.error(f"Ошибка напоминания {user_id}: {e}")

async def send_closing_reminder(bot: Bot):
    for user_id, point in EMPLOYEE_POINTS.items():
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"Заканчиваем смену!\n\nТочка: {point}\n\nНажми Закрытие смены чтобы заполнить отчёт.",
            )
        except Exception as e:
            logging.error(f"Ошибка напоминания {user_id}: {e}")

async def check_opening_done(bot: Bot):
    if not get_today_summary()["opened"]:
        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text="Прошёл час после открытия, а отчёт так и не поступил.\nПроверь точку!",
            )
        except Exception as e:
            logging.error(f"Ошибка алерта: {e}")

async def check_closing_done(bot: Bot):
    if not get_today_summary()["closed"]:
        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text="Прошёл час после закрытия, а отчёт так и не поступил.\nПроверь точку!",
            )
        except Exception as e:
            logging.error(f"Ошибка алерта: {e}")

async def send_morning_summary(bot: Bot):
    """Утренняя сводка за вчера — приходит в 09:00 МСК."""
    yesterday = get_yesterday_closing()
    now = datetime.now(MSK).strftime("%d.%m.%Y")

    if not yesterday:
        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"Доброе утро! {now}\n\nВчерашний отчёт о закрытии не поступал.",
            )
        except Exception as e:
            logging.error(f"Ошибка утренней сводки: {e}")
        return

    cash     = yesterday.get("cash", 0)
    card     = yesterday.get("card", 0)
    balance  = yesterday.get("cash_balance", 0)
    staff    = yesterday.get("staff", "не указано")
    comment  = yesterday.get("comment", "нет")
    expenses = yesterday.get("expenses", "нет")
    point    = yesterday.get("point", "?")

    text = (
        f"Доброе утро! Итоги вчерашнего дня\n\n"
        f"Точка: {point}\n"
        f"────────────────────\n"
        f"Выручка нал:     {fmt(cash)}\n"
        f"Выручка безнал:  {fmt(card)}\n"
        f"Итого:           {fmt(cash + card)}\n"
        f"Остаток в кассе: {fmt(balance)}\n"
        f"Расходы:         {expenses if expenses and expenses != 'Пропустить' else 'Нет'}\n"
        f"────────────────────\n"
        f"Смену вели: {staff}\n"
        f"Комментарий: {comment if comment and comment != 'Пропустить' else 'Нет'}"
    )

    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка утренней сводки: {e}")

async def send_daily_digest(bot: Bot):
    reports = get_today_reports()
    summary = get_today_summary()
    now     = datetime.now(MSK).strftime("%d.%m.%Y")

    text = (
        f"Дайджест за {now}\n\n"
        f"Выручка: {fmt(summary['total'])}\n"
        f"Нал: {fmt(summary['total_cash'])} | Безнал: {fmt(summary['total_card'])}\n\n"
        f"Открытие: {'✅' if summary['opened'] else '❌ не заполнено'}\n"
        f"Закрытие: {'✅' if summary['closed'] else '❌ не заполнено'}\n"
        f"Отчётов: {summary['reports_count']}"
    )

    try:
        await bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logging.error(f"Ошибка дайджеста: {e}")
        return

    if reports:
        try:
            ai_text = await analyze_day(reports)
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"ИИ-анализ дня\n\n{ai_text}",
            )
        except Exception as e:
            logging.error(f"Ошибка ИИ: {e}")

async def send_weekly_digest(bot: Bot):
    reports = [r for r in get_week_reports() if r.get("type") == "closing"]
    if not reports:
        return
    total = sum(r.get("cash", 0) + r.get("card", 0) for r in reports)
    try:
        advice = await weekly_advice(reports)
        await bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"Итоги недели\n\n"
                f"Выручка: {fmt(total)}\n"
                f"Смен: {len(reports)}\n\n"
                f"ИИ-анализ\n\n{advice}"
            ),
        )
    except Exception as e:
        logging.error(f"Ошибка еженедельного: {e}")

def setup_scheduler(bot: Bot):
    # 09:00 МСК — утренняя сводка за вчера (06:00 UTC)
    scheduler.add_job(send_morning_summary,  CronTrigger(hour=6,  minute=0),  args=[bot])
    # 10:00 МСК — напоминание об открытии
    scheduler.add_job(send_opening_reminder, CronTrigger(hour=OPENING_HOUR_UTC, minute=0), args=[bot])
    # 11:00 МСК — проверка открытия
    scheduler.add_job(check_opening_done,    CronTrigger(hour=OPENING_HOUR_UTC+1, minute=0), args=[bot])
    # 22:00 МСК — напоминание о закрытии
    scheduler.add_job(send_closing_reminder, CronTrigger(hour=CLOSING_HOUR_UTC, minute=0), args=[bot])
    # 23:00 МСК — проверка закрытия
    scheduler.add_job(check_closing_done,    CronTrigger(hour=(CLOSING_HOUR_UTC+1) % 24, minute=0), args=[bot])
    # 23:30 МСК — дайджест с ИИ
    scheduler.add_job(send_daily_digest,     CronTrigger(hour=DIGEST_HOUR_UTC, minute=30), args=[bot])
    # Воскресенье 23:00 МСК — еженедельный
    scheduler.add_job(send_weekly_digest,    CronTrigger(day_of_week="sun", hour=DIGEST_HOUR_UTC), args=[bot])

    scheduler.start()
    logging.info("Планировщик запущен.")
