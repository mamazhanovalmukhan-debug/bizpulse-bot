from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def employee_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Открыть смену")],
        [KeyboardButton(text="💰 Промежуточный отчёт"), KeyboardButton(text="🧾 Расход из кассы")],
        [KeyboardButton(text="📤 Инкассация"),           KeyboardButton(text="↩️ Возврат")],
        [KeyboardButton(text="📝 Примечание"),           KeyboardButton(text="📦 Поставка")],
        [KeyboardButton(text="🔒 Закрыть смену")],
        [KeyboardButton(text="🆘 Помощь")],
    ], resize_keyboard=True)

def kb_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )

def kb_skip_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить"),
                   KeyboardButton(text="Отмена")]],
        resize_keyboard=True, one_time_keyboard=True
    )
