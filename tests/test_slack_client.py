from __future__ import annotations

from unittest.mock import patch

import pytest

from slack_mcp_server.auth.token_store import Installation, TokenStore
from slack_mcp_server.config import ServerConfig
from slack_mcp_server.slack_client import SlackClientManager


pytestmark = pytest.mark.asyncio


def _config(**overrides: str) -> ServerConfig:
    defaults = {"client_id": "test", "client_secret": "test"}
    defaults.update(overrides)
    with patch.dict("os.environ", {f"SLACK_{k.upper()}": v for k, v in defaults.items()}, clear=False):
        return ServerConfig()  # type: ignore[call-arg]


async def test_get_client_default_workspace(token_store: TokenStore) -> None:
    await token_store.save_installation(
        Installation(
            user_id="U1",
            team_id="T1",
            user_token="xoxp-default",
            team_name="Default WS",
        )
    )
    await token_store.set_default_workspace("U1", "T1")

    manager = SlackClientManager(token_store, _config())
    client = await manager.get_client()
    assert client.token == "xoxp-default"


async def test_get_client_specific_team(token_store: TokenStore) -> None:
    await token_store.save_installation(
        Installation(user_id="U1", team_id="T1", user_token="xoxp-1")
    )
    await token_store.save_installation(
        Installation(user_id="U1", team_id="T2", user_token="xoxp-2")
    )

    manager = SlackClientManager(token_store, _config())
    client = await manager.get_client(team_id="T2")
    assert client.token == "xoxp-2"


async def test_get_client_fallback_to_first(token_store: TokenStore) -> None:
    await token_store.save_installation(
        Installation(user_id="U1", team_id="T1", user_token="xoxp-only")
    )

    manager = SlackClientManager(token_store, _config())
    client = await manager.get_client()
    assert client.token == "xoxp-only"


async def test_get_client_no_workspace(token_store: TokenStore) -> None:
    manager = SlackClientManager(token_store, _config())
    with pytest.raises(ValueError, match="No Slack workspace connected"):
        await manager.get_client()


async def test_get_client_unknown_team(token_store: TokenStore) -> None:
    await token_store.save_installation(
        Installation(user_id="U1", team_id="T1", user_token="xoxp-1")
    )

    manager = SlackClientManager(token_store, _config())
    with pytest.raises(ValueError, match="No installation found"):
        await manager.get_client(team_id="T999")


async def test_direct_token_mode(token_store: TokenStore) -> None:
    config = _config(user_token="xoxp-direct-token")
    manager = SlackClientManager(token_store, config)
    client = await manager.get_client()
    assert client.token == "xoxp-direct-token"


async def test_direct_token_ignores_db(token_store: TokenStore) -> None:
    """Direct token mode should work even with empty DB."""
    config = _config(user_token="xoxp-direct")
    manager = SlackClientManager(token_store, config)
    # No installations in DB, but should still work
    client = await manager.get_client()
    assert client.token == "xoxp-direct"
