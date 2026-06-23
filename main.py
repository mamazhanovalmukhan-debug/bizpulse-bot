import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from owner_commands import router as owner_router
from employee_menu import router as employee_router
from opening_report import router as opening_router
from closing_report import router as closing_router
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(owner_router)
    dp.include_router(employee_router)
    dp.include_router(opening_router)
    dp.include_router(closing_router)
    setup_scheduler(bot)
    print("🚀 BizPulse запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
