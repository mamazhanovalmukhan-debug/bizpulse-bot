from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from config import EMPLOYEE_POINTS

router = Router()

def is_employee(message: Message) -> bool:
    return message.from_user.id in EMPLOYEE_POINTS

def employee_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌅 Открытие смены")],
            [KeyboardButton(text="🌙 Закрытие смены")],
            [KeyboardButton(text="📊 Промежуточная выручка")],
        ],
        resize_keyboard=True,
    )

@router.message(Command("start"), is_employee)
async def employee_start(message: Message):
    name  = message.from_user.first_name
    point = EMPLOYEE_POINTS.get(message.from_user.id, "")
    await message.answer(
        f"👋 Привет, {name}!\n\n📍 Точка: *{point}*\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=employee_keyboard(),
    )

@router.message(F.text == "📊 Промежуточная выручка", is_employee)
async def interim_revenue(message: Message):
    await message.answer(
        "💰 *Промежуточная выручка*\n\n"
        "Напиши текущую сумму наличных в кассе, например: `15000`\n\n"
        "_Это не закрытие — просто фиксация на сейчас._",
        parse_mode="Markdown",
    )
