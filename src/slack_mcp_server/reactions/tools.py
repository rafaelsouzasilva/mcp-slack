from mcp.server.fastmcp import Context, FastMCP

from slack_mcp_server.slack_client import SlackClientManager


def register_reaction_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def add_reaction(
        ctx: Context,
        channel: str,
        timestamp: str,
        name: str,
    ) -> str:
        """Add an emoji reaction to a message.

        Args:
            channel: Channel ID where the message is.
            timestamp: Timestamp of the message to react to.
            name: Emoji name without colons (e.g. 'thumbsup', not ':thumbsup:').
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        await client.reactions_add(channel=channel, timestamp=timestamp, name=name)
        return f"Added :{name}: reaction"

    @mcp.tool()
    async def remove_reaction(
        ctx: Context,
        channel: str,
        timestamp: str,
        name: str,
    ) -> str:
        """Remove an emoji reaction from a message.

        Args:
            channel: Channel ID where the message is.
            timestamp: Timestamp of the message.
            name: Emoji name without colons (e.g. 'thumbsup').
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        await client.reactions_remove(channel=channel, timestamp=timestamp, name=name)
        return f"Removed :{name}: reaction"
