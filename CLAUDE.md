# Slack MCP Server

MCP server for Slack with per-user OAuth (user tokens / xoxp).

## Architecture

Package-by-feature structure under `src/slack_mcp_server/`:

- `auth/` — OAuth flow, token store (SQLite), workspace management tools
- `messaging/` — post_message, reply_to_thread
- `channels/` — list_channels, get_channel_history
- `search/` — search_messages (requires user token)
- `reactions/` — add_reaction, remove_reaction
- `server.py` — FastMCP server with lifespan, registers all tools
- `config.py` — Pydantic settings from env vars (prefix SLACK_)
- `slack_client.py` — Resolves workspace and returns AsyncWebClient

## Key Patterns

- Tools use `Context` from `mcp.server.fastmcp` (NOT `mcp.Context`) to avoid issues with `from __future__ import annotations`
- Each feature package has a `register_*_tools(mcp)` function called from `server.py`
- Lifespan pattern injects `token_store` and `config` into context dict
- Tools access context via `ctx.request_context.lifespan_context["token_store"]`
- Tokens stored in SQLite at `~/.slack-mcp-server/tokens.db`

## Development

```bash
uv sync
uv run pytest
uv run ruff check src/ tests/
```

## Running

```bash
SLACK_CLIENT_ID=... SLACK_CLIENT_SECRET=... uv run slack-mcp-server
```
