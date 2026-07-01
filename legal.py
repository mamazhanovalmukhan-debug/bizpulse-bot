"""Сотрудник v5 — полный цикл смены с кассой, складом и отчётами."""
import logging
from datetime import date, datetime
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import (
    get_business_user, get_location, get_open_shift,
    get_last_closed_shift, add_movement, add_shift_note,
    get_next_shift_notes, get_business
)
from services.shift_service import (
    start_shift, record_expense, record_collection,
    record_refund, record_deposit, do_interim_check, do_close_shift,
    get_shift_totals
)
from services.cash_service import validate_cash_report
from services.notification_service import notify_owner
from keyboards.employee import employee_main_kb, kb_cancel, kb_skip_cancel
from utils.formatting import fmt_money, parse_money

router = Router()
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════════════════════════════

class OpenShiftState(StatesGroup):
    cash_open = State()
    comment   = State()

class InterimState(StatesGroup):
    cash_actual  = State()
    expenses     = State()
    exp_note     = State()
    collection   = State()
    refunds      = State()
    note         = State()
    discr_comment = State()  # если есть расхождение

class CloseShiftState(StatesGroup):
    cash_sales       = State()
    card_sales       = State()
    aggregator_sales = State()
    expenses         = State()
    exp_note         = State()
    refunds          = State()
    collection       = State()
    deposits         = State()
    cash_actual      = State()
    discr_comment    = State()
    stock_notes      = State()
    comment          = State()

class ExpenseState(StatesGroup):
    amount  = State()
    comment = State()

class CollectionState(StatesGroup):
    amount  = State()
    comment = State()

class RefundState(StatesGroup):
    amount  = State()
    comment = State()

class NoteState(StatesGroup):
    text         = State()
    visible_next = State()


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

async def get_emp_context(tg_id: int):
    """Возвращает (business_user, location, business) или (None,None,None)."""
    bu = await get_business_user(tg_id)
    if not bu or not bu.get("location_id"):
        return None, None, None
    loc = await get_location(bu["location_id"])
    if not loc or not loc["is_active"]:
        return None, None, None
    biz = await get_business(bu["business_id"])
    if not biz or biz["is_blocked"]:
        return None, None, None
    return bu, loc, biz

def _step(current: int, total: int) -> str:
    return f"Шаг {current}/{total}"


# ═══════════════════════════════════════════════════════════════
# ОТКРЫТИЕ СМЕНЫ
# ═══════════════════════════════════════════════════════════════

@router.message(F.text == "✅ Открыть смену")
async def open_shift_start(message: Message, state: FSMContext):
    bu, loc, biz = await get_emp_context(message.from_user.id)
    if not bu:
        await message.answer("Вы не привязаны к точке. Обратитесь к владельцу.")
        return
    if await get_open_shift(loc["id"]):
        await message.answer("Смена уже открыта сегодня.", reply_markup=employee_main_kb())
        return

    last  = await get_last_closed_shift(loc["id"])
    hint  = ""
    if last and last["closing_cash"] is not None:
        hint = f"\n\nВчера в кассе на закрытии: {fmt_money(last['closing_cash'])}"

    notes = await get_next_shift_notes(loc["id"])
    notes_text = ""
    if notes:
        notes_text = "\n\n📝 Заметки с предыдущей смены:\n" + "\n".join(
            f"• {n['note']}" for n in notes
        )

    await state.update_data(
        loc_id=loc["id"], loc_name=loc["name"],
        biz_id=biz["id"], owner_id=biz["owner_id"],
        last_closing=float(last["closing_cash"]) if last and last["closing_cash"] else None
    )
    await state.set_state(OpenShiftState.cash_open)
    await message.answer(
        f"✅ Открытие смены — {loc['name']}{hint}{notes_text}\n\n"
        f"Сколько наличных в кассе прямо сейчас?\nТолько цифры:",
        reply_markup=kb_cancel()
    )

@router.message(OpenShiftState.cash_open)
async def open_shift_cash(message: Message, state: FSMContext, bot: Bot):
    amount = parse_money(message.text)
    if amount is None:
        await message.answer("Введите сумму цифрами, например: 5000")
        return
    if amount < 0:
        await message.answer("Сумма не может быть отрицательной.")
        return

    data = await state.get_data()
    last = data.get("last_closing")
    alert_text = ""
    if last is not None:
        diff = amount - last
        if abs(diff) > 10:
            direction = "больше" if diff > 0 else "меньше"
            alert_text = (
                f"\n\n⚠️ Расхождение с вчерашним закрытием!\n"
                f"Вчера: {fmt_money(last)}\nСейчас: {fmt_money(amount)}\n"
                f"Разница: {fmt_money(abs(diff))} ({direction})\n"
                f"Владелец уведомлён."
            )
            await notify_owner(
                bot, data["owner_id"],
                f"⚠️ РАСХОЖДЕНИЕ КАССЫ НА ОТКРЫТИИ\n\n"
                f"Точка: {data['loc_name']}\n"
                f"Сотрудник: {message.from_user.full_name}\n"
                f"Вчера: {fmt_money(last)}\nСейчас: {fmt_money(amount)}\n"
                f"Разница: {fmt_money(abs(diff))} ({direction})"
            )

    await state.update_data(cash_open=amount)
    await state.set_state(OpenShiftState.comment)
    await message.answer(
        f"Касса: {fmt_money(amount)} ✓{alert_text}\n\n"
        f"Замечания при открытии? Если нет — Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(OpenShiftState.comment)
async def open_shift_done(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    comment = "" if message.text == "Пропустить" else message.text.strip()
    await state.clear()

    shift_id = await start_shift(
        data["biz_id"], data["loc_id"],
        message.from_user.id, data["cash_open"], comment
    )
    now  = datetime.now().strftime("%d.%m.%Y %H:%M")
    text = (
        f"ОТКРЫТИЕ СМЕНЫ\n"
        f"Точка: {data['loc_name']}\nВремя: {now}\n"
        f"Сотрудник: {message.from_user.full_name}\n"
        f"Касса на начало: {fmt_money(data['cash_open'])}\n"
        f"Замечания: {comment or 'нет'}"
    )
    await message.answer(f"✅ Смена открыта!\n\n{text}", reply_markup=employee_main_kb())
    await notify_owner(bot, data["owner_id"], text)


# ═══════════════════════════════════════════════════════════════
# РАСХОД ИЗ КАССЫ
# ═══════════════════════════════════════════════════════════════

@router.message(F.text == "🧾 Расход из кассы")
async def expense_start(message: Message, state: FSMContext):
    bu, loc, biz = await get_emp_context(message.from_user.id)
    if not bu:
        await message.answer("Вы не привязаны к точке.")
        return
    shift = await get_open_shift(loc["id"])
    if not shift:
        await message.answer("Смена не открыта.", reply_markup=employee_main_kb())
        return
    await state.update_data(
        shift_id=shift["id"], loc_id=loc["id"],
        biz_id=biz["id"], owner_id=biz["owner_id"],
        loc_name=loc["name"], opening_cash=float(shift["opening_cash"])
    )
    await state.set_state(ExpenseState.amount)
    await message.answer("Сумма расхода? (только цифры):", reply_markup=kb_cancel())

@router.message(ExpenseState.amount)
async def expense_amount(message: Message, state: FSMContext):
    amount = parse_money(message.text)
    if amount is None or amount <= 0:
        await message.answer("Введите сумму больше нуля:")
        return
    data = await state.get_data()
    # Проверяем что расход не превышает доступные наличные
    totals = await get_shift_totals(data["shift_id"], data["opening_cash"])
    available = data["opening_cash"] + totals["cash_sales"] + totals["deposits"] - \
                totals["expenses"] - totals["refunds"] - totals["collection"]
    if amount > available:
        await message.answer(
            f"❌ Расход ({fmt_money(amount)}) превышает доступные наличные "
            f"({fmt_money(available)}).\nВведите меньшую сумму:"
        )
        return
    await state.update_data(amount=amount)
    await state.set_state(ExpenseState.comment)
    await message.answer(f"Сумма: {fmt_money(amount)} ✓\n\nНа что потрачено?")

@router.message(ExpenseState.comment)
async def expense_done(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    await record_expense(data["shift_id"], data["biz_id"], data["loc_id"],
                         data["amount"], message.text.strip(), message.from_user.id)
    text = (
        f"🧾 РАСХОД ИЗ КАССЫ\nТочка: {data['loc_name']}\n"
        f"Сумма: {fmt_money(data['amount'])}\nНазначение: {message.text.strip()}"
    )
    await message.answer(f"✅ Расход записан!\n\n{text}", reply_markup=employee_main_kb())
    await notify_owner(bot, data["owner_id"], text)


# ═══════════════════════════════════════════════════════════════
# ИНКАССАЦИЯ
# ═══════════════════════════════════════════════════════════════

@router.message(F.text == "📤 Инкассация")
async def collection_start(message: Message, state: FSMContext):
    bu, loc, biz = await get_emp_context(message.from_user.id)
    if not bu:
        return
    shift = await get_open_shift(loc["id"])
    if not shift:
        await message.answer("Смена не открыта.", reply_markup=employee_main_kb())
        return
    await state.update_data(
        shift_id=shift["id"], loc_id=loc["id"],
        biz_id=biz["id"], owner_id=biz["owner_id"],
        loc_name=loc["name"], opening_cash=float(shift["opening_cash"])
    )
    await state.set_state(CollectionState.amount)
    await message.answer("Сумма инкассации (сколько изымается из кассы):", reply_markup=kb_cancel())

@router.message(CollectionState.amount)
async def collection_amount(message: Message, state: FSMContext):
    amount = parse_money(message.text)
    if amount is None or amount <= 0:
        await message.answer("Введите сумму больше нуля:")
        return
    data = await state.get_data()
    totals = await get_shift_totals(data["shift_id"], data["opening_cash"])
    available = data["opening_cash"] + totals["cash_sales"] + totals["deposits"] - \
                totals["expenses"] - totals["refunds"] - totals["collection"]
    if amount > available:
        await message.answer(
            f"❌ Инкассация ({fmt_money(amount)}) превышает доступные наличные "
            f"({fmt_money(available)}).\nВведите меньшую сумму:"
        )
        return
    await state.update_data(amount=amount)
    await state.set_state(CollectionState.comment)
    await message.answer("Комментарий (кто забрал, куда):", reply_markup=kb_skip_cancel())

@router.message(CollectionState.comment)
async def collection_done(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    comment = "" if message.text == "Пропустить" else message.text.strip()
    await state.clear()
    await record_collection(data["shift_id"], data["biz_id"], data["loc_id"],
                            data["amount"], comment, message.from_user.id)
    text = (
        f"📤 ИНКАССАЦИЯ\nТочка: {data['loc_name']}\n"
        f"Сумма: {fmt_money(data['amount'])}\n{comment}"
    )
    await message.answer(f"✅ Инкассация записана!\n\n{text}", reply_markup=employee_main_kb())
    await notify_owner(bot, data["owner_id"], text)


# ═══════════════════════════════════════════════════════════════
# ВОЗВРАТ
# ═══════════════════════════════════════════════════════════════

@router.message(F.text == "↩️ Возврат")
async def refund_start(message: Message, state: FSMContext):
    bu, loc, biz = await get_emp_context(message.from_user.id)
    if not bu:
        return
    shift = await get_open_shift(loc["id"])
    if not shift:
        await message.answer("Смена не открыта.", reply_markup=employee_main_kb())
        return
    await state.update_data(
        shift_id=shift["id"], loc_id=loc["id"],
        biz_id=biz["id"], owner_id=biz["owner_id"],
        loc_name=loc["name"], opening_cash=float(shift["opening_cash"])
    )
    await state.set_state(RefundState.amount)
    await message.answer("Сумма возврата наличными:", reply_markup=kb_cancel())

@router.message(RefundState.amount)
async def refund_amount(message: Message, state: FSMContext):
    amount = parse_money(message.text)
    if amount is None or amount <= 0:
        await message.answer("Введите сумму больше нуля:")
        return
    await state.update_data(amount=amount)
    await state.set_state(RefundState.comment)
    await message.answer("Причина возврата:", reply_markup=kb_skip_cancel())

@router.message(RefundState.comment)
async def refund_done(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    comment = "" if message.text == "Пропустить" else message.text.strip()
    await state.clear()
    await record_refund(data["shift_id"], data["biz_id"], data["loc_id"],
                        data["amount"], comment, message.from_user.id)
    text = (
        f"↩️ ВОЗВРАТ\nТочка: {data['loc_name']}\n"
        f"Сумма: {fmt_money(data['amount'])}\n{comment}"
    )
    await message.answer(f"✅ Возврат записан!\n\n{text}", reply_markup=employee_main_kb())
    await notify_owner(bot, data["owner_id"], text)


# ═══════════════════════════════════════════════════════════════
# ПРОМЕЖУТОЧНЫЙ ОТЧЁТ
# ═══════════════════════════════════════════════════════════════

@router.message(F.text == "💰 Промежуточный отчёт")
async def interim_start(message: Message, state: FSMContext):
    bu, loc, biz = await get_emp_context(message.from_user.id)
    if not bu:
        await message.answer("Вы не привязаны к точке.")
        return
    shift = await get_open_shift(loc["id"])
    if not shift:
        await message.answer("Смена не открыта. Нажмите «✅ Открыть смену».",
                             reply_markup=employee_main_kb())
        return
    await state.update_data(
        shift_id=shift["id"], loc_id=loc["id"],
        biz_id=biz["id"], owner_id=biz["owner_id"],
        loc_name=loc["name"], opening_cash=float(shift["opening_cash"])
    )
    await state.set_state(InterimState.cash_actual)
    await message.answer(
        f"💰 Промежуточный отчёт — {loc['name']}\n\n"
        f"{_step(1,5)} Сколько наличных сейчас в кассе?\nТолько цифры:",
        reply_markup=kb_cancel()
    )

@router.message(InterimState.cash_actual)
async def interim_cash(message: Message, state: FSMContext):
    amount = parse_money(message.text)
    if amount is None:
        await message.answer("Введите сумму цифрами:")
        return
    if amount < 0:
        await message.answer("Сумма не может быть отрицательной.")
        return
    await state.update_data(cash_actual=amount)
    await state.set_state(InterimState.expenses)
    await message.answer(
        f"Наличные: {fmt_money(amount)} ✓\n\n"
        f"{_step(2,5)} Были дополнительные расходы из кассы?\nСумма или Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(InterimState.expenses)
async def interim_expenses(message: Message, state: FSMContext):
    if message.text != "Пропустить":
        amount = parse_money(message.text)
        if amount is not None and amount > 0:
            await state.update_data(extra_expenses=amount)
            await state.set_state(InterimState.exp_note)
            await message.answer(f"Расход {fmt_money(amount)} — на что?")
            return
    await state.update_data(extra_expenses=0)
    await state.set_state(InterimState.collection)
    await message.answer(
        f"{_step(3,5)} Была инкассация? Сумма или Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(InterimState.exp_note)
async def interim_exp_note(message: Message, state: FSMContext):
    await state.update_data(exp_note=message.text.strip())
    await state.set_state(InterimState.collection)
    await message.answer(
        f"{_step(3,5)} Была инкассация? Сумма или Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(InterimState.collection)
async def interim_collection(message: Message, state: FSMContext):
    amount = 0.0 if message.text == "Пропустить" else (parse_money(message.text) or 0)
    await state.update_data(extra_collection=amount)
    await state.set_state(InterimState.refunds)
    await message.answer(
        f"{_step(4,5)} Были возвраты наличными? Сумма или Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(InterimState.refunds)
async def interim_refunds(message: Message, state: FSMContext):
    amount = 0.0 if message.text == "Пропустить" else (parse_money(message.text) or 0)
    await state.update_data(extra_refunds=amount)
    await state.set_state(InterimState.note)
    await message.answer(
        f"{_step(5,5)} Есть примечание? Если нет — Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(InterimState.note)
async def interim_note(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    note = "" if message.text == "Пропустить" else message.text.strip()

    tg_id    = message.from_user.id
    shift_id = data["shift_id"]
    biz_id   = data["biz_id"]
    loc_id   = data["loc_id"]

    # Записываем движения
    extra_exp = data.get("extra_expenses", 0)
    extra_col = data.get("extra_collection", 0)
    extra_ref = data.get("extra_refunds", 0)
    if extra_exp > 0:
        await record_expense(shift_id, biz_id, loc_id, extra_exp,
                             data.get("exp_note", ""), tg_id)
    if extra_col > 0:
        await record_collection(shift_id, biz_id, loc_id, extra_col, "", tg_id)
    if extra_ref > 0:
        await record_refund(shift_id, biz_id, loc_id, extra_ref, "", tg_id)
    if note:
        await add_shift_note(biz_id, loc_id, shift_id, tg_id, note)

    emp_msg, owner_alert, discr = await do_interim_check(
        shift_id, biz_id, loc_id,
        data["opening_cash"], data["cash_actual"], tg_id,
        data["loc_name"], message.from_user.full_name
    )

    # Если большое расхождение — просим комментарий
    if discr["status"] == "alert":
        await state.update_data(emp_msg=emp_msg, owner_alert=owner_alert)
        await state.set_state(InterimState.discr_comment)
        await message.answer(
            emp_msg + "\n\n⚠️ Расхождение больше допустимого.\n"
            "Укажите причину расхождения:"
        )
        return

    await _finish_interim(message, state, bot, emp_msg, owner_alert, data)

@router.message(InterimState.discr_comment)
async def interim_discr_comment(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    emp_msg = data.get("emp_msg", "")
    owner_alert = data.get("owner_alert")
    if owner_alert:
        owner_alert += f"\n\nКомментарий сотрудника: {message.text.strip()}"
    await _finish_interim(message, state, bot, emp_msg, owner_alert, data)

async def _finish_interim(message, state, bot, emp_msg, owner_alert, data):
    await state.clear()
    await message.answer(emp_msg, reply_markup=employee_main_kb())
    if owner_alert:
        await notify_owner(bot, data["owner_id"], owner_alert)


# ═══════════════════════════════════════════════════════════════
# ПРИМЕЧАНИЕ
# ═══════════════════════════════════════════════════════════════

@router.message(F.text == "📝 Примечание")
async def note_start(message: Message, state: FSMContext):
    bu, loc, biz = await get_emp_context(message.from_user.id)
    if not bu:
        return
    shift = await get_open_shift(loc["id"])
    if not shift:
        await message.answer("Смена не открыта.", reply_markup=employee_main_kb())
        return
    await state.update_data(shift_id=shift["id"], loc_id=loc["id"],
                            biz_id=biz["id"], owner_id=biz["owner_id"])
    await state.set_state(NoteState.text)
    await message.answer("Напишите примечание:", reply_markup=kb_cancel())

@router.message(NoteState.text)
async def note_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text.strip())
    await state.set_state(NoteState.visible_next)
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    await message.answer(
        "Показать эту заметку при открытии следующей смены?",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
        ], resize_keyboard=True, one_time_keyboard=True)
    )

@router.message(NoteState.visible_next)
async def note_visible(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    visible = message.text == "Да"
    await state.clear()
    await add_shift_note(data["biz_id"], data["loc_id"], data["shift_id"],
                         message.from_user.id, data["text"], visible)
    await notify_owner(
        bot, data["owner_id"],
        f"📝 ПРИМЕЧАНИЕ\nСотрудник: {message.from_user.full_name}\n{data['text']}"
    )
    await message.answer("✅ Примечание сохранено.", reply_markup=employee_main_kb())


# ═══════════════════════════════════════════════════════════════
# ЗАКРЫТИЕ СМЕНЫ — ПОЛНЫЙ ЦИКЛ
# ═══════════════════════════════════════════════════════════════

@router.message(F.text == "🔒 Закрыть смену")
async def close_shift_start(message: Message, state: FSMContext):
    bu, loc, biz = await get_emp_context(message.from_user.id)
    if not bu:
        await message.answer("Вы не привязаны к точке.")
        return
    shift = await get_open_shift(loc["id"])
    if not shift:
        await message.answer("Смена не открыта или уже закрыта.",
                             reply_markup=employee_main_kb())
        return
    opening_cash = float(shift["opening_cash"])
    totals = await get_shift_totals(shift["id"], opening_cash)

    await state.update_data(
        shift_id=shift["id"], loc_id=loc["id"],
        biz_id=biz["id"], owner_id=biz["owner_id"],
        loc_name=loc["name"], opening_cash=opening_cash,
        # Уже записанные за смену движения (не задваиваем)
        prev_expenses=totals["expenses"],
        prev_refunds=totals["refunds"],
        prev_collection=totals["collection"],
        prev_deposits=totals["deposits"],
    )
    await state.set_state(CloseShiftState.cash_sales)
    await message.answer(
        f"🔒 Закрытие смены — {loc['name']}\n"
        f"Касса на начало: {fmt_money(opening_cash)}\n\n"
        f"{_step(1,8)} Наличные продажи за смену?\nТолько цифры (или 0):",
        reply_markup=kb_cancel()
    )

@router.message(CloseShiftState.cash_sales)
async def close_cash_sales(message: Message, state: FSMContext):
    v = parse_money(message.text)
    if v is None:
        await message.answer("Только цифры, например: 12500")
        return
    await state.update_data(cash_sales=v)
    await state.set_state(CloseShiftState.card_sales)
    await message.answer(
        f"Нал. продажи: {fmt_money(v)} ✓\n\n"
        f"{_step(2,8)} Продажи по эквайрингу (терминал)?\nТолько цифры (или 0):"
    )

@router.message(CloseShiftState.card_sales)
async def close_card_sales(message: Message, state: FSMContext):
    v = parse_money(message.text)
    if v is None:
        await message.answer("Только цифры:")
        return
    await state.update_data(card_sales=v)
    await state.set_state(CloseShiftState.aggregator_sales)
    await message.answer(
        f"Эквайринг: {fmt_money(v)} ✓\n\n"
        f"{_step(3,8)} Агрегаторы (Яндекс, Delivery и др.)?\nТолько цифры (или 0):"
    )

@router.message(CloseShiftState.aggregator_sales)
async def close_agg_sales(message: Message, state: FSMContext):
    v = parse_money(message.text)
    if v is None:
        await message.answer("Только цифры:")
        return
    await state.update_data(aggregator_sales=v)
    await state.set_state(CloseShiftState.expenses)
    await message.answer(
        f"Агрегаторы: {fmt_money(v)} ✓\n\n"
        f"{_step(4,8)} Расходы из кассы за смену?\nСумма или 0:"
    )

@router.message(CloseShiftState.expenses)
async def close_expenses(message: Message, state: FSMContext):
    v = parse_money(message.text) or 0
    if v > 0:
        await state.update_data(expenses=v)
        await state.set_state(CloseShiftState.exp_note)
        await message.answer(f"Расходы: {fmt_money(v)} ✓\n\nНа что потрачено?")
        return
    await state.update_data(expenses=0, exp_note="")
    await state.set_state(CloseShiftState.refunds)
    await message.answer(f"{_step(5,8)} Возвраты наличными? Сумма или 0:")

@router.message(CloseShiftState.exp_note)
async def close_exp_note(message: Message, state: FSMContext):
    await state.update_data(exp_note=message.text.strip())
    await state.set_state(CloseShiftState.refunds)
    await message.answer(f"{_step(5,8)} Возвраты наличными? Сумма или 0:")

@router.message(CloseShiftState.refunds)
async def close_refunds(message: Message, state: FSMContext):
    v = parse_money(message.text) or 0
    await state.update_data(refunds=v)
    await state.set_state(CloseShiftState.collection)
    await message.answer(
        f"Возвраты: {fmt_money(v)} ✓\n\n"
        f"{_step(6,8)} Инкассация (изъятие наличных)? Сумма или 0:"
    )

@router.message(CloseShiftState.collection)
async def close_collection(message: Message, state: FSMContext):
    v = parse_money(message.text) or 0
    await state.update_data(collection=v)
    await state.set_state(CloseShiftState.deposits)
    await message.answer(
        f"Инкассация: {fmt_money(v)} ✓\n\n"
        f"{_step(7,8)} Внесения в кассу (аванс, размен)? Сумма или 0:"
    )

@router.message(CloseShiftState.deposits)
async def close_deposits(message: Message, state: FSMContext):
    v = parse_money(message.text) or 0
    data = await state.get_data()
    await state.update_data(deposits=v)

    # Считаем ожидаемый остаток
    from services.cash_service import calc_expected_cash
    expected = calc_expected_cash(
        data["opening_cash"], data["cash_sales"],
        data["expenses"], data["refunds"], data["collection"], v
    )

    # Валидируем логику ПЕРЕД вводом факта
    errors = []
    available = data["opening_cash"] + data["cash_sales"] + v
    if data["expenses"] > available:
        errors.append(f"Расходы ({fmt_money(data['expenses'])}) превышают доступные наличные.")
    if data["collection"] > available:
        errors.append(f"Инкассация ({fmt_money(data['collection'])}) превышает доступные наличные.")
    if data["refunds"] > available:
        errors.append(f"Возвраты ({fmt_money(data['refunds'])}) превышают доступные наличные.")

    if errors:
        await state.update_data(deposits=v, cash_expected=expected)
        await message.answer(
            "❌ Обнаружены ошибки в данных:\n\n" + "\n".join(errors)
            + "\n\nВернитесь и исправьте данные. /cancel"
        )
        return

    await state.update_data(deposits=v, cash_expected=expected)
    await state.set_state(CloseShiftState.cash_actual)
    await message.answer(
        f"Внесения: {fmt_money(v)} ✓\n\n"
        f"{_step(8,8)} Сколько наличных в кассе сейчас (фактически)?\n"
        f"Ожидается: {fmt_money(expected)}\n\nТолько цифры:"
    )

@router.message(CloseShiftState.cash_actual)
async def close_cash_actual(message: Message, state: FSMContext):
    v = parse_money(message.text)
    if v is None:
        await message.answer("Введите сумму цифрами:")
        return
    if v < 0:
        await message.answer("Сумма не может быть отрицательной.")
        return

    data     = await state.get_data()
    expected = data.get("cash_expected", 0)
    diff     = v - expected

    from services.cash_service import check_discrepancy
    discr = check_discrepancy(expected, v)

    await state.update_data(cash_actual=v, discrepancy=diff,
                            discrepancy_status=discr["status"])

    if discr["status"] == "alert":
        await state.set_state(CloseShiftState.discr_comment)
        await message.answer(
            f"Фактически: {fmt_money(v)}\n\n"
            f"{discr['message']}\n\n"
            "Расхождение выше допустимого. Укажите причину:"
        )
        return

    await state.update_data(discr_comment="")
    await state.set_state(CloseShiftState.stock_notes)
    await message.answer(
        f"Фактически: {fmt_money(v)} ✓\n"
        + (f"\n{discr['message']}" if discr["status"] == "warning" else "") + "\n\n"
        "Что заканчивается или нужно заказать?\nЕсли всё ок — Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(CloseShiftState.discr_comment)
async def close_discr_comment(message: Message, state: FSMContext):
    await state.update_data(discr_comment=message.text.strip())
    await state.set_state(CloseShiftState.stock_notes)
    await message.answer(
        "Что заканчивается или нужно заказать?\nЕсли всё ок — Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(CloseShiftState.stock_notes)
async def close_stock_notes(message: Message, state: FSMContext):
    notes = "" if message.text == "Пропустить" else message.text.strip()
    await state.update_data(stock_notes=notes)
    await state.set_state(CloseShiftState.comment)
    await message.answer(
        "Комментарий к смене (необязательно):\nЕсли нет — Пропустить:",
        reply_markup=kb_skip_cancel()
    )

@router.message(CloseShiftState.comment)
async def close_final(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    comment = "" if message.text == "Пропустить" else message.text.strip()
    await state.clear()

    tg_id    = message.from_user.id
    shift_id = data["shift_id"]
    biz_id   = data["biz_id"]
    loc_id   = data["loc_id"]

    if data.get("stock_notes"):
        await add_shift_note(biz_id, loc_id, shift_id, tg_id,
                             data["stock_notes"], visible_next=False)

    result, owner_alert = await do_close_shift(
        shift_id=shift_id, business_id=biz_id,
        location_id=loc_id, user_id=tg_id,
        opening_cash=data["opening_cash"],
        cash_sales=data.get("cash_sales", 0),
        card_sales=data.get("card_sales", 0),
        aggregator_sales=data.get("aggregator_sales", 0),
        expenses=data.get("expenses", 0),
        refunds=data.get("refunds", 0),
        collection=data.get("collection", 0),
        deposits=data.get("deposits", 0),
        cash_actual=data["cash_actual"],
        closing_comment=comment,
        discrepancy_comment=data.get("discr_comment", ""),
        location_name=data["loc_name"],
        employee_name=message.from_user.full_name
    )

    from utils.formatting import fmt_money
    now  = datetime.now().strftime("%d.%m.%Y %H:%M")
    text = (
        f"🔒 ЗАКРЫТИЕ СМЕНЫ\n"
        f"Точка: {data['loc_name']}\nВремя: {now}\n"
        f"Сотрудник: {message.from_user.full_name}\n"
        f"{'─'*24}\n"
        f"Нал. продажи:   {fmt_money(result['cash_sales'])}\n"
        f"Эквайринг:      {fmt_money(result['card_sales'])}\n"
        f"Агрегаторы:     {fmt_money(result['aggregator_sales'])}\n"
        f"Итого выручка:  {fmt_money(result['total_sales'])}\n"
        f"Расходы:        {fmt_money(result['expenses'])}\n"
        f"Возвраты:       {fmt_money(result['refunds'])}\n"
        f"Инкассация:     {fmt_money(result['collection'])}\n"
        f"{'─'*24}\n"
        f"Ожидаемая касса: {fmt_money(result['cash_expected'])}\n"
        f"Фактическая:     {fmt_money(result['cash_actual'])}\n"
        f"{result['discrepancy_message']}"
        + (f"\nЧто заканчивается: {data['stock_notes']}" if data.get("stock_notes") else "")
        + (f"\nКомментарий: {comment}" if comment else "")
    )

    await message.answer(f"{text}\n\nХорошего отдыха! 🌙",
                         reply_markup=employee_main_kb())
    # Владельцу — полный отчёт
    await notify_owner(bot, data["owner_id"],
                       text + (f"\n\n{owner_alert}" if owner_alert else ""))


# ── ПОСТАВКА (заглушка) ──────────────────────────────────────────────────────

@router.message(F.text == "📦 Поставка")
async def delivery_stub(message: Message):
    bu, loc, biz = await get_emp_context(message.from_user.id)
    if not bu:
        return
    await message.answer(
        "📦 Поставки\n\n"
        f"Точка: {loc['name']}\n\n"
        "Модуль приёмки поставок подключается в ближайшем обновлении.\n"
        "По вопросам поставок обратитесь к владельцу.",
        reply_markup=employee_main_kb()
    )
