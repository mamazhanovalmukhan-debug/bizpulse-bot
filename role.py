from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def owner_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Статус сейчас"),   KeyboardButton(text="📊 Итоги дня")],
        [KeyboardButton(text="📈 Итоги недели"),    KeyboardButton(text="🤖 ИИ-анализ")],
        [KeyboardButton(text="🧠 Советник"),         KeyboardButton(text="📊 Health Score")],
        [KeyboardButton(text="🧾 Касса"),            KeyboardButton(text="👥 Сотрудники")],
        [KeyboardButton(text="🏪 Точки"),            KeyboardButton(text="📦 Склад")],
        [KeyboardButton(text="💳 Подписка"),         KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="🆘 Поддержка")],
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

def kb_yes_no() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]],
        resize_keyboard=True, one_time_keyboard=True
    )

def locations_kb(locations: list) -> ReplyKeyboardMarkup:
    rows  = [[KeyboardButton(text=l["name"])] for l in locations]
    rows += [[KeyboardButton(text="Отмена")]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                               one_time_keyboard=True)

def roles_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Сотрудник"), KeyboardButton(text="Менеджер")],
        [KeyboardButton(text="Отмена")],
    ], resize_keyboard=True, one_time_keyboard=True)

def categories_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Кофейня"),          KeyboardButton(text="Шаурма")],
        [KeyboardButton(text="Табачный магазин"),  KeyboardButton(text="Пекарня")],
        [KeyboardButton(text="Магазин"),           KeyboardButton(text="Другое")],
    ], resize_keyboard=True, one_time_keyboard=True)

def timezones_kb() -> ReplyKeyboardMarkup:
    from utils.dates import TIMEZONES
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for _, label in TIMEZONES],
        resize_keyboard=True, one_time_keyboard=True
    )
