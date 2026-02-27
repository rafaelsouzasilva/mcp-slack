from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    model_config = {"env_prefix": "SLACK_"}

    # Direct token mode (simple, personal use)
    user_token: str | None = Field(
        default=None,
        description="Direct user token (xoxp-...). Skips OAuth entirely.",
    )

    # OAuth mode (team use)
    client_id: str | None = Field(default=None, description="Slack app client ID")
    client_secret: str | None = Field(
        default=None, description="Slack app client secret"
    )

    redirect_port: int = Field(default=9876, description="Local OAuth callback port")

    mcp_transport: str = Field(
        default="stdio",
        alias="SLACK_MCP_TRANSPORT",
        description="MCP transport: stdio or streamable-http",
    )

    token_db_path: Path = Field(
        default=Path.home() / ".slack-mcp-server" / "tokens.db",
        alias="SLACK_TOKEN_DB_PATH",
        description="Path to SQLite token database",
    )

    user_scopes: str = Field(
        default=",".join([
            "channels:read",
            "groups:read",
            "channels:history",
            "groups:history",
            "chat:write",
            "search:read",
            "reactions:write",
            "reactions:read",
            "users:read",
        ]),
        alias="SLACK_USER_SCOPES",
        description="Comma-separated OAuth user scopes",
    )

    @property
    def is_direct_token_mode(self) -> bool:
        return self.user_token is not None

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.redirect_port}/callback"
