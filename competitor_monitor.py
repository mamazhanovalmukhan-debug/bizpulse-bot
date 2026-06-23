import httpx
import logging
import re
from config import GROQ_KEY

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

COMPETITOR_CHANNELS = [
    {"name": "Stars Coffee",  "username": "starscoffee"},
    {"name": "Surf Coffee",   "username": "surfcoffeexmsk"},
    {"name": "Кофемания",     "username": "coffeemaniaru"},
]

def clean_text(text: str) -> str:
    """Убирает HTML теги и лишние символы."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Экранируем символы которые ломают Markdown в Telegram
    for ch in ['*', '_', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(ch, ' ')
    return text[:300]

async def fetch_channel_posts(username: str, limit: int = 3) -> list[str]:
    """Читает последние посты из публичного Telegram-канала."""
    url = f"https://t.me/s/{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    posts = []
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logging.warning(f"{username}: статус {resp.status_code}")
                return []
            html = resp.text
            pattern = r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>'
            raw_posts = re.findall(pattern, html, re.DOTALL)
            for raw in raw_posts[:limit]:
                clean = clean_text(raw)
                if len(clean) > 15:
                    posts.append(clean)
    except Exception as e:
        logging.error(f"Ошибка парсинга {username}: {e}")
    return posts

async def ask_groq(prompt: str, system: str = "") -> str:
    if not GROQ_KEY:
        return "GROQ_API_KEY не настроен."
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
        "max_tokens": 500,
        "temperature": 0.7,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=payload)
            data = resp.json()
            if "choices" not in data:
                return f"Ошибка ИИ: {data.get('error', {}).get('message', 'неизвестно')}"
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"Groq ошибка: {e}")
        return "Не удалось получить ответ от ИИ."

async def get_competitor_intelligence() -> str:
    """Собирает посты конкурентов и делает ИИ-анализ."""
    all_posts = {}
    posts_text = ""

    for ch in COMPETITOR_CHANNELS:
        posts = await fetch_channel_posts(ch["username"])
        if posts:
            all_posts[ch["name"]] = posts
            posts_text += f"\n{ch['name']}:\n"
            for p in posts:
                posts_text += f"- {p}\n"

    if not all_posts:
        return (
            "Не удалось получить посты конкурентов с сервера.\n"
            "Каналы могут быть недоступны с американского сервера Railway.\n"
            "Попробуй через час."
        )

    system = (
        "Ты аналитик конкурентной разведки для кофейни на Красной площади в Москве. "
        "Изучи посты конкурентов и дай 1-2 конкретных совета владельцу. "
        "Каждый совет начинается с названия конкурента. "
        "Пример: 'Stars Coffee анонсировали летний напиток — добавьте похожую позицию до выходных'. "
        "Только русский язык. Без markdown форматирования."
    )

    prompt = (
        f"Последние посты конкурентов:{posts_text}\n\n"
        "Дай 1-2 конкретных совета что сделать прямо сейчас на основе активности конкурентов."
    )

    return await ask_groq(prompt, system)

async def get_raw_competitor_posts() -> str:
    """Возвращает сырые посты конкурентов."""
    result = "Последние посты конкурентов\n\n"
    found_any = False

    for ch in COMPETITOR_CHANNELS:
        posts = await fetch_channel_posts(ch["username"], limit=2)
        if posts:
            found_any = True
            result += f"{ch['name']} (@{ch['username']})\n"
            for p in posts:
                result += f"- {p}\n"
            result += "\n"

    if not found_any:
        result += "Посты недоступны с сервера. Каналы могут быть закрыты или заблокированы."

    return result
