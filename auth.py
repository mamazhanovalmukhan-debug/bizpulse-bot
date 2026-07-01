from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Статистика"),     KeyboardButton(text="💳 Платежи")],
        [KeyboardButton(text="🏢 Бизнесы"),        KeyboardButton(text="📢 Рассылка")],
        [KeyboardButton(text="✅ Активировать"),    KeyboardButton(text="🚫 Заблокировать")],
    ], resize_keyboard=True)
