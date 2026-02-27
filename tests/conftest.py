from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from slack_mcp_server.auth.token_store import TokenStore
from slack_mcp_server.config import ServerConfig


@pytest.fixture
async def token_store(tmp_path: Path) -> TokenStore:
    store = TokenStore(tmp_path / "test_tokens.db")
    await store.initialize()
    yield store  # type: ignore[misc]
    await store.close()


@pytest.fixture
def config() -> ServerConfig:
    env = {"SLACK_CLIENT_ID": "test", "SLACK_CLIENT_SECRET": "test"}
    with patch.dict("os.environ", env, clear=False):
        return ServerConfig()  # type: ignore[call-arg]
