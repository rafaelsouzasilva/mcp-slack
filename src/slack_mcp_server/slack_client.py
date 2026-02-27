from __future__ import annotations

from slack_sdk.web.async_client import AsyncWebClient

from slack_mcp_server.auth.token_store import Installation, TokenStore
from slack_mcp_server.config import ServerConfig


class SlackClientManager:
    def __init__(self, token_store: TokenStore, config: ServerConfig) -> None:
        self._store = token_store
        self._config = config

    async def get_client(self, team_id: str | None = None) -> AsyncWebClient:
        # Direct token mode — skip all DB lookups
        if self._config.is_direct_token_mode:
            return AsyncWebClient(token=self._config.user_token)

        installation = await self._resolve_workspace(team_id)
        return AsyncWebClient(token=installation.user_token)

    async def _resolve_workspace(self, team_id: str | None = None) -> Installation:
        if team_id:
            installations = await self._store.list_installations()
            for inst in installations:
                if inst.team_id == team_id:
                    return inst
            raise ValueError(f"No installation found for team {team_id}")

        default = await self._store.get_default_workspace()
        if default:
            user_id, t_id = default
            inst = await self._store.get_installation(user_id, t_id)
            if inst:
                return inst

        installations = await self._store.list_installations()
        if installations:
            return installations[0]

        raise ValueError(
            "No Slack workspace connected. Use slack_authenticate to connect."
        )
