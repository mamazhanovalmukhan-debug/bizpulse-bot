import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from config import OWNER_ID, EMPLOYEE_POINTS, OPENING_HOUR_UTC, CLOSING_HOUR_UTC, DIGEST_HOUR_UTC
from storage import get_today_summary, get_today_reports, get_week_reports
from ai_analyst import analyze_day, weekly_advice

scheduler = AsyncIOScheduler()

async def send_opening_reminder(bot: Bot):
    for user_id, point in EMPLOYEE_POINTS.items():
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"☀️ *Доброе утро!*\n\n📍 {point}\n\nНажми *🌅 Открытие смены*",
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Ошибка напоминания об открытии {user_id}: {e}")

async def send_closing_reminder(bot: Bot):
    for user_id, point in EMPLOYEE_POINTS.items():
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🌙 *Заканчиваем смену!*\n\n📍 {point}\n\nНажми *🌙 Закрытие смены*",
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Ошибка напоминания о закрытии {user_id}: {e}")

async def check_opening_done(bot: Bot):
    if not get_today_summary()["opened"]:
        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text="⚠️ *Внимание!*\n\nЧас прошёл, а отчёт об открытии так и не поступил.\nПроверь точку!",
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Ошибка алерта об открытии: {e}")

async def check_closing_done(bot: Bot):
    if not get_today_summary()["closed"]:
        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text="⚠️ *Внимание!*\n\nЧас прошёл, а отчёт о закрытии так и не поступил.\nПроверь точку!",
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Ошибка алерта о закрытии: {e}")

async def send_daily_digest(bot: Bot):
    reports = get_today_reports()
    summary = get_today_summary()
    now     = datetime.now().strftime("%d.%m.%Y")

    def fmt(x): return f"{x:,.0f} ₽".replace(",", " ")

    text = (
        f"📊 *Дайджест за {now}*\n\n"
        f"💰 Выручка: *{fmt(summary['total'])}*\n"
        f"  Нал: {fmt(summary['total_cash'])} | Безнал: {fmt(summary['total_card'])}\n\n"
        f"🌅 Открытие: {'✅' if summary['opened'] else '❌'}\n"
        f"🌙 Закрытие: {'✅' if summary['closed'] else '❌'}\n"
        f"📋 Отчётов: {summary['reports_count']}"
    )
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка дайджеста: {e}")
        return

    if reports:
        try:
            ai_text = await analyze_day(reports)
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"🤖 *ИИ-анализ дня*\n\n{ai_text}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Ошибка ИИ-дайджеста: {e}")

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
                f"📅 *Итоги недели*\n\n"
                f"💰 Выручка: *{total:,.0f} ₽*\n"
                f"📋 Смен: {len(reports)}\n\n"
                f"🤖 *Анализ ИИ*\n\n{advice}"
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Ошибка еженедельного дайджеста: {e}")

def setup_scheduler(bot: Bot):
    scheduler.add_job(send_opening_reminder, CronTrigger(hour=OPENING_HOUR_UTC, minute=0), args=[bot])
    scheduler.add_job(check_opening_done,    CronTrigger(hour=OPENING_HOUR_UTC + 1, minute=0), args=[bot])
    scheduler.add_job(send_closing_reminder, CronTrigger(hour=CLOSING_HOUR_UTC, minute=0), args=[bot])
    scheduler.add_job(check_closing_done,    CronTrigger(hour=(CLOSING_HOUR_UTC + 1) % 24, minute=0), args=[bot])
    scheduler.add_job(send_daily_digest,     CronTrigger(hour=DIGEST_HOUR_UTC, minute=30), args=[bot])
    scheduler.add_job(send_weekly_digest,    CronTrigger(day_of_week="sun", hour=DIGEST_HOUR_UTC, minute=0), args=[bot])
    scheduler.start()
    logging.info("✅ Планировщик запущен.")
