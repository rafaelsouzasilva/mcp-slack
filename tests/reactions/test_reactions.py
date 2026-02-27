from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from slack_mcp_server.auth.token_store import Installation, TokenStore
from slack_mcp_server.config import ServerConfig


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def setup_workspace(token_store: TokenStore) -> TokenStore:
    await token_store.save_installation(
        Installation(user_id="U1", team_id="T1", user_token="xoxp-test")
    )
    await token_store.set_default_workspace("U1", "T1")
    return token_store


async def test_add_reaction(setup_workspace: TokenStore, config: ServerConfig) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(return_value={"ok": True})

    with patch.object(AsyncWebClient, "reactions_add", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.reactions_add(
            channel="C001", timestamp="100.001", name="thumbsup"
        )
        assert result["ok"] is True


async def test_remove_reaction(setup_workspace: TokenStore, config: ServerConfig) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(return_value={"ok": True})

    with patch.object(AsyncWebClient, "reactions_remove", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.reactions_remove(
            channel="C001", timestamp="100.001", name="thumbsup"
        )
        assert result["ok"] is True
