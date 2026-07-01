"""Централизованная конфигурация BizPulse v6."""
import os
from dataclasses import dataclass, field
import logging

# ═══════════════════════════════════════════════════════
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ═══════════════════════════════════════════════════════

def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Приглушаем слишком шумные библиотеки
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@dataclass
class Config:
    # ── Telegram ──────────────────────────────────────
    BOT_TOKEN: str     = os.getenv("BOT_TOKEN", "")
    BOT_USERNAME: str  = os.getenv("BOT_USERNAME", "bizpulse_bot")

    # ── Database ──────────────────────────────────────
    DATABASE_URL: str  = os.getenv("DATABASE_URL", "")

    # ── AI ────────────────────────────────────────────
    GROQ_API_KEY: str  = os.getenv("GROQ_API_KEY", "")

    # ── Payments ──────────────────────────────────────
    PAYMENT_PROVIDER_TOKEN: str = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
    PAYMENT_CURRENCY: str       = os.getenv("PAYMENT_CURRENCY", "RUB")

    # ── Admin ─────────────────────────────────────────
    ADMIN_IDS: set     = None
    SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "@bizpulse_support")

    # ── Legal ─────────────────────────────────────────
    OFFER_URL: str             = os.getenv("OFFER_URL", "")
    PRIVACY_POLICY_URL: str    = os.getenv("PRIVACY_POLICY_URL", "")

    # ── Security ──────────────────────────────────────
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # ── Debug ─────────────────────────────────────────
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ══════════════════════════════════════════════════
    # БИЗНЕС-ЛОГИКА — все настройки в одном месте
    # ══════════════════════════════════════════════════

    # Trial
    DEFAULT_TRIAL_DAYS: int      = int(os.getenv("DEFAULT_TRIAL_DAYS", "30"))

    # Тарифные лимиты
    PLAN_EMPLOYEES_LIMIT: int    = int(os.getenv("PLAN_EMPLOYEES_LIMIT", "10"))

    # Кассовая логика
    CASH_TOLERANCE_AMOUNT: float = float(os.getenv("CASH_TOLERANCE_AMOUNT", "100"))
    CASH_MAX_AMOUNT: float       = float(os.getenv("CASH_MAX_AMOUNT", "10000000"))  # 10M ₽

    # Аналитика
    MIN_SHIFTS_FOR_ANALYTICS: int   = int(os.getenv("MIN_SHIFTS_FOR_ANALYTICS", "5"))
    ANOMALY_DROP_PERCENT: float     = float(os.getenv("ANOMALY_DROP_PERCENT", "30"))
    ANOMALY_EXPENSE_PERCENT: float  = float(os.getenv("ANOMALY_EXPENSE_PERCENT", "50"))

    # Склад
    LOW_STOCK_ALERT_ENABLED: bool   = os.getenv("LOW_STOCK_ALERT_ENABLED", "true").lower() == "true"

    # Health Score
    HEALTH_SCORE_ENABLED: bool  = os.getenv("HEALTH_SCORE_ENABLED", "true").lower() == "true"

    # Отчёты
    REPORT_TIME_UTC_HOUR: int   = int(os.getenv("REPORT_TIME_UTC_HOUR", "20"))

    # Валидация строк
    MAX_NAME_LENGTH: int         = 100
    MAX_COMMENT_LENGTH: int      = 500

    def __post_init__(self):
        # Собираем ADMIN_IDS из ADMIN_IDS + OWNER_ID (для совместимости с Railway)
        raw_admin = os.getenv("ADMIN_IDS", "")
        raw_owner = os.getenv("OWNER_ID", "")
        ids_str   = raw_admin + "," + raw_owner
        self.ADMIN_IDS = {int(x) for x in ids_str.split(",") if x.strip().isdigit()}

config = Config()
