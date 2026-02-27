from mcp.server.fastmcp import Context, FastMCP

from slack_mcp_server.slack_client import SlackClientManager


def register_channel_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_channels(
        ctx: Context,
        limit: int = 100,
        cursor: str | None = None,
        types: str = "public_channel,private_channel",
    ) -> str:
        """List channels in the Slack workspace.

        Args:
            limit: Max number of channels to return (default 100).
            cursor: Pagination cursor for next page.
            types: Comma-separated channel types (public_channel, private_channel).
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        kwargs: dict = {"limit": limit, "types": types}
        if cursor:
            kwargs["cursor"] = cursor

        response = await client.conversations_list(**kwargs)
        channels = response.get("channels", [])

        if not channels:
            return "No channels found."

        lines = []
        for ch in channels:
            name = ch.get("name", "unknown")
            ch_id = ch.get("id", "")
            purpose = ch.get("purpose", {}).get("value", "")
            member_count = ch.get("num_members", "?")
            prefix = "#" if not ch.get("is_private") else "🔒"
            line = f"- {prefix}{name} ({ch_id}) [{member_count} members]"
            if purpose:
                line += f" — {purpose}"
            lines.append(line)

        result = "\n".join(lines)

        next_cursor = (
            response.get("response_metadata", {}).get("next_cursor", "") or ""
        )
        if next_cursor:
            result += f"\n\n(More results available, use cursor: '{next_cursor}')"

        return result

    @mcp.tool()
    async def get_channel_history(
        ctx: Context,
        channel: str,
        limit: int = 20,
        oldest: str | None = None,
        latest: str | None = None,
    ) -> str:
        """Read message history from a Slack channel.

        Args:
            channel: Channel ID to read from.
            limit: Max number of messages to return (default 20).
            oldest: Only messages after this Unix timestamp.
            latest: Only messages before this Unix timestamp.
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        kwargs: dict = {"channel": channel, "limit": limit}
        if oldest:
            kwargs["oldest"] = oldest
        if latest:
            kwargs["latest"] = latest

        response = await client.conversations_history(**kwargs)
        messages = response.get("messages", [])

        if not messages:
            return "No messages found."

        lines = []
        for msg in reversed(messages):
            user = msg.get("user", "unknown")
            text = msg.get("text", "")
            ts = msg.get("ts", "")
            thread = (
                f" [thread: {msg.get('reply_count', 0)} replies]"
                if msg.get("reply_count")
                else ""
            )
            lines.append(f"[{ts}] <{user}> {text}{thread}")

        return "\n".join(lines)
