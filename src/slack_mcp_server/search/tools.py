from mcp.server.fastmcp import Context, FastMCP

from slack_mcp_server.slack_client import SlackClientManager


def register_search_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def search_messages(
        ctx: Context,
        query: str,
        sort: str = "timestamp",
        sort_dir: str = "desc",
        count: int = 20,
    ) -> str:
        """Search for messages across the Slack workspace.

        Requires a user token (xoxp) — this tool uses the authenticated user's
        search:read scope.

        Args:
            query: Search query (supports Slack search syntax like 'in:#channel from:@user').
            sort: Sort by 'score' or 'timestamp' (default: timestamp).
            sort_dir: Sort direction 'asc' or 'desc' (default: desc).
            count: Max results to return (default 20).
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        response = await client.search_messages(
            query=query, sort=sort, sort_dir=sort_dir, count=count
        )

        matches = response.get("messages", {}).get("matches", [])
        total = response.get("messages", {}).get("total", 0)

        if not matches:
            return f"No messages found for query: '{query}'"

        lines = [f"Found {total} results (showing {len(matches)}):"]
        for msg in matches:
            user = msg.get("username", msg.get("user", "unknown"))
            text = msg.get("text", "")
            ts = msg.get("ts", "")
            channel_name = msg.get("channel", {}).get("name", "unknown")
            permalink = msg.get("permalink", "")

            if len(text) > 200:
                text = text[:200] + "..."

            lines.append(f"\n[{ts}] #{channel_name} <{user}> {text}")
            if permalink:
                lines.append(f"  Link: {permalink}")

        return "\n".join(lines)
