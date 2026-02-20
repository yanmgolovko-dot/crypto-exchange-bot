"""Кэширование данных с истечением срока действия"""

import time
from typing import Optional, Any, Dict
from bot.config.settings import config


class TTLCache:
    """Простой кэш с временем жизни (TTL) в памяти."""

    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}

    def set(self, key: str, value: Any):
        """Сохранить значение с текущей меткой времени."""
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def get(self, key: str) -> Optional[Any]:
        """Получить значение, если оно не устарело."""
        if key not in self._cache:
            return None
        timestamp = self._timestamps.get(key, 0)
        if time.time() - timestamp > self.ttl_seconds:
            # Просрочено
            self.delete(key)
            return None
        return self._cache[key]

    def delete(self, key: str):
        """Удалить запись из кэша."""
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

    def clear(self):
        """Очистить весь кэш."""
        self._cache.clear()
        self._timestamps.clear()


# Единый экземпляр для курсов, TTL берётся из конфига
rate_cache = TTLCache(ttl_seconds=config.RATE_CACHE_TTL)