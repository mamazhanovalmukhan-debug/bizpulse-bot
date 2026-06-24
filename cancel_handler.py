from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from config import OWNER_ID, EMPLOYEE_POINTS

router = Router()

def employee_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открытие смены")],
            [KeyboardButton(text="Закрытие смены")],
            [KeyboardButton(text="Промежуточная выручка")],
            [KeyboardButton(text="Предложение")],
        ],
        resize_keyboard=True,
    )

def owner_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Статус сейчас"),    KeyboardButton(text="Итоги дня")],
            [KeyboardButton(text="ИИ-анализ дня"),    KeyboardButton(text="Разведка")],
            [KeyboardButton(text="Анализ остатков"),   KeyboardButton(text="Итоги недели")],
            [KeyboardButton(text="Добавить поставку"), KeyboardButton(text="Поставки")],
        ],
        resize_keyboard=True,
    )

@router.message(F.text.lower().in_(["отмена", "отменить", "назад", "/отмена", "/cancel"]))
async def cancel_any_fsm(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        # Нет активного FSM — просто возвращаем меню
        if message.from_user.id == OWNER_ID:
            await message.answer("Главное меню:", reply_markup=owner_keyboard())
        elif message.from_user.id in EMPLOYEE_POINTS:
            await message.answer("Главное меню:", reply_markup=employee_keyboard())
        return
    await state.clear()
    if message.from_user.id == OWNER_ID:
        await message.answer("Действие отменено.", reply_markup=owner_keyboard())
    elif message.from_user.id in EMPLOYEE_POINTS:
        await message.answer("Действие отменено.", reply_markup=employee_keyboard())
    else:
        await message.answer("Действие отменено.")
