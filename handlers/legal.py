"""Юридические документы и поддержка."""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from config import config

router = Router()

@router.message(Command("legal"))
async def cmd_legal(message: Message):
    lines = ["📋 Юридическая информация\n"]
    if config.OFFER_URL:
        lines.append(f"📄 Оферта: {config.OFFER_URL}")
    if config.PRIVACY_POLICY_URL:
        lines.append(f"🔒 Политика данных: {config.PRIVACY_POLICY_URL}")
    lines.append(f"🆘 Поддержка: {config.SUPPORT_USERNAME}")
    lines.append(
        "\n⚠️ Владелец сервиса самостоятельно подключает платёжный провайдер "
        "и несёт ответственность за фискальные операции."
    )
    await message.answer("\n".join(lines))

@router.message(Command("myid"))
async def my_id(message: Message):
    user = message.from_user
    await message.answer(
        f"Ваш Telegram ID: `{user.id}`\n"
        f"Имя: {user.full_name}",
        parse_mode="Markdown"
    )
