"""BizPulse v6 — Production entry point."""
import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import config, setup_logging, get_logger
from database.session import create_pool, close_pool
from middlewares.auth import AuthMiddleware
from middlewares.role import RoleMiddleware
from middlewares.subscription import SubscriptionMiddleware
from middlewares.error_handler import ErrorHandlerMiddleware
from handlers.cancel import router as cancel_router
from handlers.start import router as start_router
from handlers.onboarding import router as onboarding_router
from handlers.billing import router as billing_router
from handlers.owner import router as owner_router
from handlers.employee import router as employee_router
from handlers.payments import router as payments_router
from handlers.admin import router as admin_router
from handlers.legal import router as legal_router
from handlers.support import router as support_router
from handlers.demo import router as demo_router
from scheduler.setup import setup_scheduler

setup_logging(debug=config.DEBUG)
log = get_logger("main")

MIGRATIONS = [
    "001_init.sql",
    "002_v3.sql",
    "003_plans.sql",
    "004_production.sql",
    "005_fix_plans_and_trial.sql",
]

async def run_migrations(pool):
    base = os.path.dirname(__file__)
    for fname in MIGRATIONS:
        path = os.path.join(base, "database", "migrations", fname)
        if not os.path.exists(path):
            log.warning(f"Migration not found: {fname}")
            continue
        with open(path) as f:
            sql = f.read()
        try:
            await pool.execute(sql)
            log.info(f"Migration OK: {fname}")
        except Exception as e:
            log.error(f"Migration ERROR {fname}: {e}")
            raise

async def main():
    if not config.BOT_TOKEN:
        log.critical("BOT_TOKEN is not set!")
        return
    if not config.DATABASE_URL:
        log.critical("DATABASE_URL is not set!")
        return
    if not config.ADMIN_IDS:
        log.warning("ADMIN_IDS is empty — admin commands won't work")

    bot  = Bot(token=config.BOT_TOKEN)
    dp   = Dispatcher(storage=MemoryStorage())
    pool = await create_pool()
    await run_migrations(pool)
    log.info("Database ready.")

    # Middleware — порядок критичен
    for obs in (dp.message, dp.callback_query):
        obs.middleware(ErrorHandlerMiddleware())   # 1. ловим все ошибки
        obs.middleware(AuthMiddleware())           # 2. rate limit + upsert
        obs.middleware(RoleMiddleware())           # 3. определяем роль
        obs.middleware(SubscriptionMiddleware())   # 4. проверяем подписку

    # Роутеры — cancel ПЕРВЫМ, payments ДО subscription-блока
    dp.include_router(cancel_router)
    dp.include_router(start_router)
    dp.include_router(onboarding_router)
    dp.include_router(payments_router)
    dp.include_router(billing_router)
    dp.include_router(admin_router)
    dp.include_router(legal_router)
    dp.include_router(support_router)
    dp.include_router(demo_router)
    dp.include_router(owner_router)
    dp.include_router(employee_router)

    setup_scheduler(bot)
    log.info(f"BizPulse v6 started! Bot: @{config.BOT_USERNAME}")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "pre_checkout_query"]
        )
    finally:
        await close_pool()
        log.info("BizPulse stopped.")

if __name__ == "__main__":
    asyncio.run(main())
