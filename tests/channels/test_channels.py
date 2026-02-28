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


async def test_list_channels(setup_workspace: TokenStore, config: ServerConfig) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(
        return_value={
            "ok": True,
            "channels": [
                {
                    "id": "C001",
                    "name": "general",
                    "is_private": False,
                    "num_members": 42,
                    "purpose": {"value": "Company-wide announcements"},
                },
                {
                    "id": "C002",
                    "name": "random",
                    "is_private": False,
                    "num_members": 38,
                    "purpose": {"value": ""},
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }
    )

    with patch.object(AsyncWebClient, "conversations_list", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.conversations_list(limit=100, types="public_channel")
        assert result["ok"] is True
        assert len(result["channels"]) == 2


async def test_get_channel_history(setup_workspace: TokenStore, config: ServerConfig) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(
        return_value={
            "ok": True,
            "messages": [
                {"user": "U1", "text": "Hello world", "ts": "100.001"},
                {
                    "user": "U2",
                    "text": "Thread starter",
                    "ts": "100.002",
                    "reply_count": 3,
                },
            ],
        }
    )

    with patch.object(AsyncWebClient, "conversations_history", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.conversations_history(channel="C001", limit=20)
        assert result["ok"] is True
        assert len(result["messages"]) == 2


async def test_get_thread_replies(
    setup_workspace: TokenStore, config: ServerConfig
) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(
        return_value={
            "ok": True,
            "messages": [
                {"user": "U1", "text": "Thread starter", "ts": "100.002"},
                {"user": "U2", "text": "First reply", "ts": "100.003"},
                {
                    "user": "U3",
                    "text": "Second reply",
                    "ts": "100.004",
                    "reactions": [{"name": "thumbsup", "count": 2}],
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }
    )

    with patch.object(AsyncWebClient, "conversations_replies", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.conversations_replies(
            channel="C001", ts="100.002", limit=50
        )
        assert result["ok"] is True
        assert len(result["messages"]) == 3
        assert result["messages"][0]["ts"] == "100.002"


async def test_get_thread_replies_empty(
    setup_workspace: TokenStore, config: ServerConfig
) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(
        return_value={
            "ok": True,
            "messages": [],
        }
    )

    with patch.object(AsyncWebClient, "conversations_replies", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.conversations_replies(
            channel="C001", ts="999.999", limit=50
        )
        assert result["ok"] is True
        assert len(result["messages"]) == 0
