"""POS-адаптер kontur_market — STUB — подключить API: реализовать реальный API."""
from services.pos.base import POSAdapter
import logging

class KonturMarketAdapter(POSAdapter):
    async def test_connection(self) -> bool:
        logging.warning("kontur_market adapter not implemented yet")
        return False

    async def sync_transactions(self, from_dt, to_dt) -> list:
        # STUB — подключить API: реализовать запрос к API kontur_market
        return []

    async def get_daily_sales(self, date) -> dict:
        # STUB — подключить API: GET /api/sales?date=...
        return {"cash": 0, "card": 0, "sbp": 0, "total": 0}

    async def get_products(self) -> list:
        # STUB — подключить API: GET /api/products
        return []

    async def get_sales_by_product(self, from_dt, to_dt) -> list:
        # STUB — подключить API: GET /api/sales/by-product
        return []
