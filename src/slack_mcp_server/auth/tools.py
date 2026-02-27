from mcp.server.fastmcp import Context, FastMCP

from slack_mcp_server.auth.flow import OAuthFlow
from slack_mcp_server.auth.token_store import TokenStore
from slack_mcp_server.config import ServerConfig


def register_auth_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def slack_authenticate(ctx: Context) -> str:
        """Authenticate with Slack via OAuth.

        Opens the browser for you to authorize with your Slack account.
        After authorizing, the token is stored locally for future use.
        Not needed if SLACK_USER_TOKEN is set directly.
        """
        app_ctx = ctx.request_context.lifespan_context
        config: ServerConfig = app_ctx["config"]

        if config.is_direct_token_mode:
            return "Already configured with a direct user token (SLACK_USER_TOKEN). No OAuth needed."

        if not config.client_id or not config.client_secret:
            return (
                "OAuth requires SLACK_CLIENT_ID and SLACK_CLIENT_SECRET. "
                "Alternatively, set SLACK_USER_TOKEN for direct token mode."
            )

        flow = OAuthFlow(config=config, token_store=app_ctx["token_store"])
        return await flow.authenticate()

    @mcp.tool()
    async def slack_list_workspaces(ctx: Context) -> str:
        """List all connected Slack workspaces."""
        app_ctx = ctx.request_context.lifespan_context
        config: ServerConfig = app_ctx["config"]

        if config.is_direct_token_mode:
            return "Using direct token mode (SLACK_USER_TOKEN). Single workspace."

        token_store: TokenStore = app_ctx["token_store"]
        installations = await token_store.list_installations()

        if not installations:
            return "No workspaces connected. Use slack_authenticate to connect."

        default = await token_store.get_default_workspace()
        default_key = (default[0], default[1]) if default else None

        lines = []
        for inst in installations:
            is_default = (
                " (default)" if (inst.user_id, inst.team_id) == default_key else ""
            )
            lines.append(
                f"- {inst.team_name} ({inst.team_id}) as @{inst.user_name}{is_default}"
            )

        return "Connected workspaces:\n" + "\n".join(lines)

    @mcp.tool()
    async def slack_set_default_workspace(ctx: Context, team_id: str) -> str:
        """Set the default Slack workspace.

        Args:
            team_id: The team ID of the workspace to set as default.
        """
        token_store: TokenStore = ctx.request_context.lifespan_context["token_store"]
        installations = await token_store.list_installations()

        for inst in installations:
            if inst.team_id == team_id:
                await token_store.set_default_workspace(inst.user_id, team_id)
                return f"Default workspace set to '{inst.team_name}' ({team_id})"

        return f"No installation found for team {team_id}"

    @mcp.tool()
    async def slack_remove_workspace(ctx: Context, team_id: str) -> str:
        """Remove a connected Slack workspace.

        Args:
            team_id: The team ID of the workspace to remove.
        """
        token_store: TokenStore = ctx.request_context.lifespan_context["token_store"]
        installations = await token_store.list_installations()

        for inst in installations:
            if inst.team_id == team_id:
                await token_store.remove_installation(inst.user_id, team_id)

                # Clear default if it was this workspace
                default = await token_store.get_default_workspace()
                if default and default[1] == team_id:
                    remaining = await token_store.list_installations()
                    if remaining:
                        await token_store.set_default_workspace(
                            remaining[0].user_id, remaining[0].team_id
                        )

                return f"Removed workspace '{inst.team_name}' ({team_id})"

        return f"No installation found for team {team_id}"
