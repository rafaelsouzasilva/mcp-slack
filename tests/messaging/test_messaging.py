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


async def test_post_message(setup_workspace: TokenStore, config: ServerConfig) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(
        return_value={"ok": True, "ts": "123.456", "channel": "C123"}
    )

    with patch.object(AsyncWebClient, "chat_postMessage", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.chat_postMessage(channel="C123", text="Hello")
        assert result["ok"] is True
        mock_response.assert_called_once_with(channel="C123", text="Hello")


async def test_reply_to_thread(setup_workspace: TokenStore, config: ServerConfig) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(return_value={"ok": True, "ts": "123.789"})

    with patch.object(AsyncWebClient, "chat_postMessage", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.chat_postMessage(
            channel="C123", text="Reply", thread_ts="123.456"
        )
        assert result["ok"] is True
