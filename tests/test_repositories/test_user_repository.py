import pytest
from bot.services.db.user_repository import UserRepository


@pytest.mark.asyncio
async def test_add_and_get_user(db):
    repo = UserRepository(db._connection)

    user_id = 12345
    username = "testuser"
    first_name = "Test"
    last_name = "User"

    await repo.add_or_update_user(user_id, username, first_name, last_name)

    user = await repo.get_user(user_id)
    assert user is not None
    assert user.user_id == user_id
    assert user.username == username
    assert user.first_name == first_name
    assert user.last_name == last_name
    assert user.is_banned == False


@pytest.mark.asyncio
async def test_ban_user(db):
    repo = UserRepository(db._connection)

    user_id = 12345
    await repo.add_or_update_user(user_id)

    await repo.ban_user(user_id, "spam", banned_by=999)

    user = await repo.get_user(user_id)
    assert user.is_banned == True
    assert user.ban_reason == "spam"
    assert user.banned_by == 999

    banned, reason = await repo.is_user_banned(user_id)
    assert banned is True
    assert reason == "spam"