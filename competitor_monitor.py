import httpx
import logging
from datetime import datetime, timedelta
from config import GROQ_KEY

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Публичные Telegram-каналы конкурентов
COMPETITOR_CHANNELS = [
    {"name": "Stars Coffee",  "username": "starscoffee"},
    {"name": "Surf Coffee",   "username": "surfcoffeexmsk"},
    {"name": "Кофемания",     "username": "coffeemaniaru"},
]

async def fetch_channel_posts(username: str, limit: int = 5) -> list[dict]:
    """Читает последние посты из публичного Telegram-канала через t.me/s/."""
    url = f"https://t.me/s/{username}"
    headers = {"User-Agent": "Mozilla/5.0"}
    posts = []
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return []
            html = resp.text

            # Простой парсинг без lxml — ищем текст постов
            import re
            # Извлекаем тексты постов
            pattern = r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>'
            raw_posts = re.findall(pattern, html, re.DOTALL)

            for raw in raw_posts[:limit]:
                # Убираем HTML теги
                clean = re.sub(r'<[^>]+>', ' ', raw)
                clean = re.sub(r'\s+', ' ', clean).strip()
                if len(clean) > 20:
                    posts.append({"text": clean[:500]})

    except Exception as e:
        logging.error(f"Ошибка парсинга {username}: {e}")
    return posts

async def ask_groq(prompt: str, system: str = "") -> str:
    if not GROQ_KEY:
        return "⚠️ GROQ_API_KEY не настроен."
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": 600,
        "temperature": 0.7,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=payload)
            data = resp.json()
            if "choices" not in data:
                return f"⚠️ Ошибка ИИ: {data.get('error', {}).get('message', 'неизвестно')}"
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"Groq ошибка: {e}")
        return "⚠️ Не удалось получить ответ от ИИ."

async def get_competitor_intelligence() -> str:
    """Собирает посты конкурентов и делает ИИ-анализ."""
    all_posts = {}
    posts_found = False

    for ch in COMPETITOR_CHANNELS:
        posts = await fetch_channel_posts(ch["username"])
        if posts:
            all_posts[ch["name"]] = posts
            posts_found = True

    if not posts_found:
        return (
            "⚠️ Не удалось получить посты конкурентов.\n\n"
            "Возможно, каналы закрыты или недоступны с сервера.\n"
            "Попробуй позже или проверь доступность каналов."
        )

    # Формируем текст для ИИ
    context = ""
    for name, posts in all_posts.items():
        context += f"\n=== {name} ===\n"
        for i, p in enumerate(posts, 1):
            context += f"{i}. {p['text']}\n"

    system = (
        "Ты аналитик конкурентной разведки для кофейни на Красной площади в Москве. "
        "Анализируй посты конкурентов и давай КОНКРЕТНЫЕ советы владельцу. "
        "Формат: 1-2 совета, каждый начинается с названия конкурента. "
        "Совет должен быть действием — что именно сделать сегодня или завтра. "
        "Примеры хороших советов: "
        "'Stars Coffee запустили летний напиток с маракуйей — добавьте аналогичную позицию до выходных'; "
        "'Кофемания анонсировала акцию 2+1 на холодные напитки — введите похожую промо до конца недели'. "
        "Отвечай только на русском языке."
    )

    prompt = (
        f"Последние посты конкурентов наших кофеен:\n{context}\n\n"
        "Дай 1-2 конкретных совета что нам нужно сделать прямо сейчас "
        "на основе активности конкурентов. Каждый совет — одно конкретное действие."
    )

    return await ask_groq(prompt, system)

async def get_raw_competitor_posts() -> str:
    """Возвращает сырые посты конкурентов для просмотра."""
    result = "📱 *Последние посты конкурентов*\n\n"
    found_any = False

    for ch in COMPETITOR_CHANNELS:
        posts = await fetch_channel_posts(ch["username"], limit=3)
        if posts:
            found_any = True
            result += f"*{ch['name']}* (@{ch['username']})\n"
            for p in posts:
                result += f"• {p['text'][:200]}...\n"
            result += "\n"

    if not found_any:
        result += "⚠️ Посты недоступны — каналы могут быть закрыты или заблокированы с сервера."

    return result
