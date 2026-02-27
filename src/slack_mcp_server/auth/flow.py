from __future__ import annotations

import secrets
import webbrowser
from urllib.parse import urlencode

from slack_sdk.web.async_client import AsyncWebClient

from slack_mcp_server.auth.http_server import OAuthCallbackServer
from slack_mcp_server.auth.token_store import Installation, TokenStore
from slack_mcp_server.config import ServerConfig


class OAuthFlow:
    def __init__(self, config: ServerConfig, token_store: TokenStore) -> None:
        self._config = config
        self._store = token_store

    def build_authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._config.client_id,
            "user_scope": self._config.user_scopes,
            "redirect_uri": self._config.redirect_uri,
            "state": state,
        }
        return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"

    async def authenticate(self) -> str:
        """Run the full OAuth flow. Returns a status message."""
        state = secrets.token_urlsafe(32)
        await self._store.save_oauth_state(state)

        authorize_url = self.build_authorize_url(state)
        webbrowser.open(authorize_url)

        callback_server = OAuthCallbackServer(port=self._config.redirect_port)
        result = await callback_server.wait_for_callback(timeout=300)

        if "error" in result and result["error"]:
            return f"Authentication failed: {result['error']}"

        code = result.get("code")
        returned_state = result.get("state")

        if not code:
            return "Authentication failed: no code received"

        if not returned_state or not await self._store.validate_oauth_state(
            returned_state
        ):
            return "Authentication failed: invalid state parameter"

        # Exchange code for token
        client = AsyncWebClient()
        response = await client.oauth_v2_access(
            client_id=self._config.client_id,
            client_secret=self._config.client_secret,
            code=code,
            redirect_uri=self._config.redirect_uri,
        )

        authed_user = response.get("authed_user", {})
        user_token = authed_user.get("access_token")
        if not user_token:
            return "Authentication failed: no user token in response"

        team = response.get("team", {})
        team_id = team.get("id", "")
        team_name = team.get("name", "")
        user_id = authed_user.get("id", "")

        # Get user info for display name
        user_client = AsyncWebClient(token=user_token)
        user_info = await user_client.users_info(user=user_id)
        user_name = (
            user_info.get("user", {}).get("profile", {}).get("display_name")
            or user_info.get("user", {}).get("real_name")
            or user_id
        )

        installation = Installation(
            user_id=user_id,
            team_id=team_id,
            user_token=user_token,
            user_token_expires_at=authed_user.get("expires_in"),
            user_refresh_token=authed_user.get("refresh_token"),
            user_scopes=authed_user.get("scope"),
            team_name=team_name,
            user_name=user_name,
        )
        await self._store.save_installation(installation)

        # Auto-set as default if it's the first workspace
        installations = await self._store.list_installations()
        if len(installations) == 1:
            await self._store.set_default_workspace(user_id, team_id)

        return f"Authenticated as @{user_name} in workspace '{team_name}' ({team_id})"
