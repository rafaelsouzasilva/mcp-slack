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


async def test_search_messages(setup_workspace: TokenStore, config: ServerConfig) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(
        return_value={
            "ok": True,
            "messages": {
                "total": 2,
                "matches": [
                    {
                        "user": "U1",
                        "username": "testuser",
                        "text": "Found message 1",
                        "ts": "200.001",
                        "channel": {"name": "general"},
                        "permalink": "https://slack.com/archives/C001/p200001",
                    },
                    {
                        "user": "U2",
                        "username": "other",
                        "text": "Found message 2",
                        "ts": "200.002",
                        "channel": {"name": "random"},
                        "permalink": "https://slack.com/archives/C002/p200002",
                    },
                ],
            },
        }
    )

    with patch.object(AsyncWebClient, "search_messages", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.search_messages(query="test", count=20)
        assert result["ok"] is True
        assert result["messages"]["total"] == 2


async def test_search_no_results(setup_workspace: TokenStore, config: ServerConfig) -> None:
    from slack_sdk.web.async_client import AsyncWebClient

    mock_response = AsyncMock(
        return_value={
            "ok": True,
            "messages": {"total": 0, "matches": []},
        }
    )

    with patch.object(AsyncWebClient, "search_messages", mock_response):
        from slack_mcp_server.slack_client import SlackClientManager

        manager = SlackClientManager(setup_workspace, config)
        client = await manager.get_client()
        result = await client.search_messages(query="nonexistent")
        assert result["messages"]["total"] == 0
