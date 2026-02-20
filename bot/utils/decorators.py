"""Декораторы и rate limiter"""

from datetime import datetime
from functools import wraps
import asyncio

class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}

    def is_allowed(self, user_id: int) -> bool:
        now = datetime.now()
        if user_id not in self.requests:
            self.requests[user_id] = []
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if (now - req_time).seconds < self.window_seconds
        ]
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        self.requests[user_id].append(now)
        return True

    def get_remaining(self, user_id: int) -> int:
        if user_id not in self.requests:
            return self.max_requests
        now = datetime.now()
        recent_requests = [
            req_time for req_time in self.requests[user_id]
            if (now - req_time).seconds < self.window_seconds
        ]
        return max(0, self.max_requests - len(recent_requests))

rate_limiter = RateLimiter(max_requests=20, window_seconds=60)

def db_retry(max_retries=3):
    """Декоратор для повторных попыток при ошибках БД"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(self, *args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(0.1 * (attempt + 1))
            return None
        return wrapper
    return decorator