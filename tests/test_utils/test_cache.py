import time
from bot.services.cache import TTLCache


def test_ttl_cache():
    cache = TTLCache(ttl_seconds=1)
    cache.set("key", "value")
    assert cache.get("key") == "value"
    time.sleep(1.1)
    assert cache.get("key") is None