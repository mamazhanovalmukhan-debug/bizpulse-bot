"""Ручной ввод данных — без POS интеграции."""
from services.pos.base import POSAdapter

class ManualAdapter(POSAdapter):
    async def test_connection(self) -> bool:
        return True  # Ручной режим всегда доступен

    async def sync_transactions(self, from_dt, to_dt) -> list:
        return []  # Нет внешнего источника

    async def get_daily_sales(self, date) -> dict:
        return {"cash": 0, "card": 0, "sbp": 0, "total": 0}

    async def get_products(self) -> list:
        return []

    async def get_sales_by_product(self, from_dt, to_dt) -> list:
        return []
