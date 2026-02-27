from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from slack_mcp_server.auth.token_store import TokenStore
from slack_mcp_server.config import ServerConfig


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    config = ServerConfig()  # type: ignore[call-arg]
    token_store = TokenStore(config.token_db_path)
    await token_store.initialize()
    try:
        yield {"token_store": token_store, "config": config}
    finally:
        await token_store.close()


mcp = FastMCP("slack", lifespan=app_lifespan)

# Register all tools from feature packages
from slack_mcp_server.auth.tools import register_auth_tools  # noqa: E402
from slack_mcp_server.channels.tools import register_channel_tools  # noqa: E402
from slack_mcp_server.messaging.tools import register_messaging_tools  # noqa: E402
from slack_mcp_server.reactions.tools import register_reaction_tools  # noqa: E402
from slack_mcp_server.search.tools import register_search_tools  # noqa: E402

register_auth_tools(mcp)
register_messaging_tools(mcp)
register_channel_tools(mcp)
register_search_tools(mcp)
register_reaction_tools(mcp)
