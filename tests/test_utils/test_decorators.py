import pytest
from bot.utils.decorators import RateLimiter, rate_limiter, db_retry


def test_rate_limiter():
    limiter = RateLimiter(max_requests=2, window_seconds=10)
    user_id = 1

    assert limiter.is_allowed(user_id) is True
    assert limiter.is_allowed(user_id) is True
    assert limiter.is_allowed(user_id) is False

    assert limiter.get_remaining(user_id) == 0


@pytest.mark.asyncio
async def test_db_retry():
    class TestRepo:
        attempt = 0

        @db_retry(max_retries=3)
        async def failing_method(self):
            self.attempt += 1
            if self.attempt < 3:
                raise Exception("DB error")
            return "success"

    repo = TestRepo()
    result = await repo.failing_method()
    assert result == "success"
    assert repo.attempt == 3