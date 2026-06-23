import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Токен не найден. Добавь BOT_TOKEN в переменные окружения Railway.")
