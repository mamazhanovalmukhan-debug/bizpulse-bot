"""Настройка APScheduler."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from scheduler.jobs import (
    job_hourly_location_checks,
    job_weekly_digest,
    job_subscription_reminders,
    job_expire_subscriptions,
    job_nightly_health_check,
    job_morning_advisor,
)

scheduler = AsyncIOScheduler(timezone="UTC")

def setup_scheduler(bot: Bot):
    # Каждый час — проверяем каждую точку по её локальному open/close_time
    scheduler.add_job(
        job_hourly_location_checks,
        CronTrigger(minute=0),   # каждый час ровно
        args=[bot],
        id="hourly_location_checks",
        replace_existing=True,
    )
    # Воскресенье 19:00 UTC — еженедельный дайджест
    scheduler.add_job(
        job_weekly_digest,
        CronTrigger(day_of_week="sun", hour=19),
        args=[bot],
        id="weekly_digest",
        replace_existing=True,
    )
    # Каждый день 12:00 UTC — напоминания о подписке (за 3 дня и 1 день)
    scheduler.add_job(
        job_subscription_reminders,
        CronTrigger(hour=12, minute=0),
        args=[bot],
        id="sub_reminders",
        replace_existing=True,
    )
    # Каждый час — проверка истёкших подписок
    scheduler.add_job(
        job_expire_subscriptions,
        CronTrigger(minute=30),
        args=[bot],
        id="expire_subs",
        replace_existing=True,
    )
    # Ночной health check в 02:00 UTC
    scheduler.add_job(
        job_nightly_health_check,
        CronTrigger(hour=2, minute=0),
        args=[bot],
        id="nightly_health",
        replace_existing=True,
    )
    # Утренний советник 07:00 МСК = 04:00 UTC
    scheduler.add_job(
        job_morning_advisor,
        CronTrigger(hour=4, minute=0),
        args=[bot],
        id="morning_advisor",
        replace_existing=True,
    )
    scheduler.start()
    logging.info("Scheduler started: %d jobs.", len(scheduler.get_jobs()))
