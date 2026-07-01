"""Базовый интерфейс для POS-интеграций."""
from abc import ABC, abstractmethod
from typing import Optional

class POSAdapter(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def test_connection(self) -> bool: ...

    @abstractmethod
    async def sync_transactions(self, from_dt, to_dt) -> list: ...

    @abstractmethod
    async def get_daily_sales(self, date) -> dict: ...

    @abstractmethod
    async def get_products(self) -> list: ...

    @abstractmethod
    async def get_sales_by_product(self, from_dt, to_dt) -> list: ...
