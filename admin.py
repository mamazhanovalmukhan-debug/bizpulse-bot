"""Пул соединений asyncpg."""
import asyncpg
import logging
from typing import Optional

_pool: Optional[asyncpg.Pool] = None

async def create_pool() -> asyncpg.Pool:
    global _pool
    from config import config  # MED-3 FIX: через config, не напрямую
    _pool = await asyncpg.create_pool(
        config.DATABASE_URL,
        min_size=2, max_size=15,
        command_timeout=30,
    )
    return _pool

def get_pool() -> asyncpg.Pool:
    # MED-1 FIX: явная ошибка если pool не инициализирован
    if _pool is None:
        raise RuntimeError(
            "Database pool is not initialized. "
            "Call 'await create_pool()' before using get_pool()."
        )
    return _pool

async def close_pool():
    if _pool:
        await _pool.close()
