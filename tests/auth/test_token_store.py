from __future__ import annotations

import pytest

from slack_mcp_server.auth.token_store import Installation, TokenStore


pytestmark = pytest.mark.asyncio


async def test_save_and_get_installation(token_store: TokenStore) -> None:
    inst = Installation(
        user_id="U123",
        team_id="T456",
        user_token="xoxp-test-token",
        team_name="Test Workspace",
        user_name="testuser",
    )
    await token_store.save_installation(inst)

    result = await token_store.get_installation("U123", "T456")
    assert result is not None
    assert result.user_token == "xoxp-test-token"
    assert result.team_name == "Test Workspace"
    assert result.user_name == "testuser"


async def test_get_missing_installation(token_store: TokenStore) -> None:
    result = await token_store.get_installation("U999", "T999")
    assert result is None


async def test_upsert_installation(token_store: TokenStore) -> None:
    inst = Installation(
        user_id="U123",
        team_id="T456",
        user_token="xoxp-old-token",
        team_name="Old Name",
        user_name="old",
    )
    await token_store.save_installation(inst)

    inst.user_token = "xoxp-new-token"
    inst.team_name = "New Name"
    await token_store.save_installation(inst)

    result = await token_store.get_installation("U123", "T456")
    assert result is not None
    assert result.user_token == "xoxp-new-token"
    assert result.team_name == "New Name"


async def test_list_installations(token_store: TokenStore) -> None:
    for i in range(3):
        await token_store.save_installation(
            Installation(
                user_id=f"U{i}",
                team_id=f"T{i}",
                user_token=f"xoxp-{i}",
            )
        )

    results = await token_store.list_installations()
    assert len(results) == 3


async def test_remove_installation(token_store: TokenStore) -> None:
    await token_store.save_installation(
        Installation(user_id="U1", team_id="T1", user_token="xoxp-1")
    )

    removed = await token_store.remove_installation("U1", "T1")
    assert removed is True

    result = await token_store.get_installation("U1", "T1")
    assert result is None


async def test_remove_missing_installation(token_store: TokenStore) -> None:
    removed = await token_store.remove_installation("U999", "T999")
    assert removed is False


async def test_default_workspace(token_store: TokenStore) -> None:
    assert await token_store.get_default_workspace() is None

    await token_store.set_default_workspace("U1", "T1")
    result = await token_store.get_default_workspace()
    assert result == ("U1", "T1")

    # Override
    await token_store.set_default_workspace("U2", "T2")
    result = await token_store.get_default_workspace()
    assert result == ("U2", "T2")


async def test_oauth_state_valid(token_store: TokenStore) -> None:
    await token_store.save_oauth_state("test-state", ttl=60)
    valid = await token_store.validate_oauth_state("test-state")
    assert valid is True

    # Should be consumed (deleted)
    valid = await token_store.validate_oauth_state("test-state")
    assert valid is False


async def test_oauth_state_expired(token_store: TokenStore) -> None:
    await token_store.save_oauth_state("expired-state", ttl=-1)
    valid = await token_store.validate_oauth_state("expired-state")
    assert valid is False


async def test_oauth_state_missing(token_store: TokenStore) -> None:
    valid = await token_store.validate_oauth_state("nonexistent")
    assert valid is False


async def test_cleanup_expired_states(token_store: TokenStore) -> None:
    await token_store.save_oauth_state("fresh", ttl=600)
    await token_store.save_oauth_state("stale", ttl=-1)

    await token_store.cleanup_expired_states()

    assert await token_store.validate_oauth_state("fresh") is True
    assert await token_store.validate_oauth_state("stale") is False
