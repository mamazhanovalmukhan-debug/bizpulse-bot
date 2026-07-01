"""ИИ-аналитика v3 — без конкурентов, с данными склада."""
import httpx
import logging
from config import config
from database.models import save_ai_report

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """Ты бизнес-аналитик для малого бизнеса в России (кофейни, шаурма, пекарни, магазины).

Стиль ответов:
— Конкретно, без воды
— Не категорично: "можно попробовать", "стоит проверить"
— Измеримые предложения: "увеличить на 20%", "протестировать 7 дней"
— Если мало данных — честно говори об этом

Формат ответа:
📊 Что произошло
💡 Почему важно
💸 Где теряем деньги
✅ Что попробовать завтра
📈 Ожидаемый эффект
⚠️ Что проверить"""

async def _ask_groq(prompt: str, max_tokens: int = 1200) -> str:
    if not config.GROQ_API_KEY:
        return "⚠️ GROQ_API_KEY не настроен в переменных Railway."
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }
    try:
        async with httpx.AsyncClient(timeout=35) as c:
            r = await c.post(GROQ_URL, headers=headers, json=payload)
            if r.status_code == 401:
                return "⚠️ Неверный GROQ_API_KEY."
            if r.status_code == 429:
                return "⚠️ Превышен лимит Groq. Попробуйте через минуту."
            data = r.json()
            if "choices" not in data:
                err = data.get("error", {}).get("message", str(data))[:200]
                return f"⚠️ Ошибка Groq: {err}"
            return data["choices"][0]["message"]["content"].strip()
    except httpx.TimeoutException:
        return "⚠️ ИИ не отвечает (таймаут). Попробуйте позже."
    except Exception as e:
        logging.error(f"Groq error: {e}")
        return f"⚠️ Ошибка ИИ: {type(e).__name__}"

async def analyze_day(business_id: int, biz_name: str, biz_category: str,
                       reports: list, movements: list, notes: list,
                       low_stock: list = None) -> str:
    from utils.formatting import fmt_money, CATEGORY_NAMES
    cat = CATEGORY_NAMES.get(biz_category, biz_category)

    cash_t = sum(m["amount"] for m in movements if m["type"] == "sale_cash")
    card_t = sum(m["amount"] for m in movements if m["type"] == "sale_card")
    exp_t  = sum(m["amount"] for m in movements if m["type"] == "expense")
    discr  = [r for r in reports if r.get("discrepancy") and abs(r["discrepancy"]) > 10]
    notes_text = "\n".join(f"- {n}" for n in notes) if notes else "нет заметок"
    stock_text = ""
    if low_stock:
        stock_text = "\nОстатки ниже минимума: " + ", ".join(
            p["name"] for p in low_stock
        )

    prompt = (
        f"Бизнес: {biz_name} ({cat})\n"
        f"Выручка нал: {fmt_money(cash_t)}, безнал: {fmt_money(card_t)}, "
        f"расходы: {fmt_money(exp_t)}\n"
        f"Расхождений кассы: {len(discr)}\n"
        f"Заметки: {notes_text}{stock_text}\n\n"
        f"Дай анализ дня по формату."
    )
    result = await _ask_groq(prompt)
    await save_ai_report(business_id, "daily", result)
    return result

async def analyze_week(business_id: int, biz_name: str,
                        reports: list, movements: list) -> str:
    from utils.formatting import fmt_money
    total = sum(
        (m["amount"] or 0) for m in movements
        if m["type"].startswith("sale_")
    )
    expenses = sum(
        (m["amount"] or 0) for m in movements
        if m["type"] == "expense"
    )
    discr = [r for r in reports if r.get("discrepancy") and abs(r["discrepancy"]) > 10]

    prompt = (
        f"Бизнес: {biz_name}\n"
        f"За 7 дней: выручка {fmt_money(total)}, расходы {fmt_money(expenses)}, "
        f"расхождений: {len(discr)}\n"
        f"Смен закрыто: {len([r for r in reports if r['report_type']=='closing'])}\n\n"
        f"Дай еженедельный анализ по формату."
    )
    result = await _ask_groq(prompt)
    await save_ai_report(business_id, "weekly", result)
    return result

async def analyze_stock(business_id: int, biz_name: str, notes: list,
                         low_stock: list = None) -> str:
    if not notes and not low_stock:
        return "Данных об остатках нет. Добавьте товары через раздел Склад."
    notes_text = "\n".join(f"- {n}" for n in notes[:30]) if notes else ""
    low_text = ""
    if low_stock:
        low_text = "\nТовары ниже минимума:\n" + "\n".join(
            f"- {p['name']}: {p['current_stock']} {p['unit']} "
            f"(мин. {p['min_stock']})"
            for p in low_stock
        )
    prompt = (
        f"Бизнес: {biz_name}\n"
        f"Заметки об остатках:\n{notes_text}{low_text}\n\n"
        f"Выяви что регулярно заканчивается. "
        f"Предложи оптимальный график заказов."
    )
    return await _ask_groq(prompt)
