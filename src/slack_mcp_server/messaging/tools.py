from mcp.server.fastmcp import Context, FastMCP

from slack_mcp_server.slack_client import SlackClientManager


def register_messaging_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def post_message(
        ctx: Context,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> str:
        """Post a message to a Slack channel as the authenticated user.

        Args:
            channel: Channel ID or name to post to.
            text: Message text (supports Slack markdown).
            thread_ts: Optional thread timestamp to reply in a thread.
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        kwargs: dict = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts

        response = await client.chat_postMessage(**kwargs)
        ts = response.get("ts", "")
        ch = response.get("channel", channel)
        return f"Message posted to {ch} (ts: {ts})"

    @mcp.tool()
    async def reply_to_thread(
        ctx: Context,
        channel: str,
        thread_ts: str,
        text: str,
    ) -> str:
        """Reply to a specific thread in a Slack channel.

        Args:
            channel: Channel ID where the thread is.
            thread_ts: Timestamp of the parent message.
            text: Reply text (supports Slack markdown).
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        response = await client.chat_postMessage(
            channel=channel, text=text, thread_ts=thread_ts
        )
        ts = response.get("ts", "")
        return f"Reply posted (ts: {ts})"
