import httpx
import logging
from config import COMPETITORS, GROQ_KEY

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

async def ask_groq(prompt: str, system: str = "") -> str:
    if not GROQ_KEY:
        return (
            "⚠️ ИИ не настроен.\n"
            "Добавь переменную GROQ_API_KEY в настройках Railway:\n"
            "Settings → Variables → Add Variable"
        )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama3-70b-8192",
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0.7,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=payload)
            data = resp.json()

            # Явная обработка ошибок API
            if resp.status_code == 401:
                return "⚠️ Неверный GROQ_API_KEY. Проверь ключ в переменных Railway."
            if resp.status_code == 429:
                return "⚠️ Превышен лимит запросов Groq. Попробуй через минуту."
            if "choices" not in data:
                err = data.get("error", {}).get("message", str(data))
                logging.error(f"Groq API ошибка: {err}")
                return f"⚠️ Ошибка ИИ: {err[:200]}"

            return data["choices"][0]["message"]["content"].strip()
    except httpx.TimeoutException:
        return "⚠️ ИИ не отвечает (таймаут 30 сек). Попробуй позже."
    except Exception as e:
        logging.error(f"Groq ошибка: {e}")
        return f"⚠️ Не удалось получить ответ от ИИ: {type(e).__name__}"

async def analyze_day(reports: list[dict]) -> str:
    system = (
        "Ты бизнес-аналитик кофейни на Красной площади в Москве. "
        "Анализируй данные кратко, по делу, на русском языке. "
        "Максимум 5 пунктов."
    )
    comp_info = "\n".join([
        f"- {c['name']}: чек {c['avg_check']}₽, рейтинг {c['rating']}"
        for c in COMPETITORS
    ])
    reports_text = ""
    for r in reports:
        reports_text += (
            f"Точка: {r.get('point', '?')}\n"
            f"Касса начало: {r.get('cash_open', 0)}₽\n"
            f"Выручка: нал {r.get('cash', 0)}₽, безнал {r.get('card', 0)}₽, "
            f"итого {r.get('cash', 0) + r.get('card', 0)}₽\n"
            f"Расходы: {r.get('expenses', 'нет')}\n"
            f"Остатки: {r.get('stock_notes', 'без замечаний')}\n"
            f"Происшествия: {r.get('incidents', 'нет')}\n\n"
        )
    prompt = (
        f"Данные за сегодня:\n{reports_text}\n"
        f"Конкуренты рядом:\n{comp_info}\n\n"
        "Дай краткий анализ дня, выдели сильные и слабые стороны, "
        "предложи 2-3 конкретных действия на завтра."
    )
    return await ask_groq(prompt, system)

async def analyze_competitors() -> str:
    system = (
        "Ты эксперт по ресторанному бизнесу в Москве. "
        "Отвечай кратко, конкретно, на русском."
    )
    comp_info = "\n".join([
        f"- {c['name']} ({c['address']}): чек {c['avg_check']}₽, рейтинг {c['rating']}"
        for c in COMPETITORS
    ])
    prompt = (
        f"Наша кофейня на Красной площади в Москве. "
        f"Конкуренты:\n{comp_info}\n\n"
        "Дай 3-5 конкретных рекомендаций как выделиться. "
        "Учти туристический трафик Красной площади."
    )
    return await ask_groq(prompt, system)

async def weekly_advice(week_reports: list[dict]) -> str:
    system = (
        "Ты бизнес-консультант для кофейни. "
        "Отвечай структурировано, кратко, на русском."
    )
    total = sum(r.get("cash", 0) + r.get("card", 0) for r in week_reports)
    days  = len(week_reports) or 1
    avg   = total / days
    prompt = (
        f"За неделю кофейня собрала {total:,.0f}₽ за {days} дней, "
        f"среднедневная {avg:,.0f}₽.\n\n"
        "Что хорошо, что улучшить, 3 действия на следующую неделю."
    )
    return await ask_groq(prompt, system)

async def analyze_stock(stock_notes: list[str]) -> str:
    if not stock_notes:
        return "Данных об остатках нет."
    system = "Ты управляющий кофейней. Отвечай кратко на русском."
    notes_text = "\n".join(f"- {n}" for n in stock_notes if n and n != "Пропустить")
    if not notes_text:
        return "Замечаний по остаткам не было."
    prompt = (
        f"Записи об остатках:\n{notes_text}\n\n"
        "Выдели что регулярно заканчивается и предложи график заказа."
    )
    return await ask_groq(prompt, system)
