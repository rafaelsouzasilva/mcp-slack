from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP

from slack_mcp_server.files.download import DEFAULT_DOWNLOAD_DIR, FileDownloadError, download_file
from slack_mcp_server.slack_client import SlackClientManager


def register_file_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_file(
        ctx: Context,
        file_id: str,
        dest_dir: str | None = None,
    ) -> str:
        """Download a file shared in Slack and return its local path.

        Text files (markdown, plain text, csv, json, yaml, code) up to 512 KB
        also have their content returned inline. File ids appear in message
        listings as [file: name (F0123..., mimetype)]. Requires the files:read
        user scope.

        Args:
            file_id: Slack file id (starts with F).
            dest_dir: Directory to save into (default ~/Downloads/slack-mcp).
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        target = Path(dest_dir).expanduser() if dest_dir else DEFAULT_DOWNLOAD_DIR
        try:
            downloaded = await download_file(client, file_id, target)
        except FileDownloadError as exc:
            return f"Could not download {file_id}: {exc}"

        header = (
            f"Saved {downloaded.name} ({downloaded.mimetype}, {downloaded.size} bytes) "
            f"to {downloaded.path}"
        )
        if downloaded.text is None:
            return header
        return f"{header}\n\n{downloaded.text}"
