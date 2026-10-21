from mcp.server.fastmcp import Context, FastMCP

from slack_mcp_server.files.download import (
    DEFAULT_DOWNLOAD_DIR,
    INLINE_TEXT_LIMIT_BYTES,
    FileDownloadError,
    download_file,
)
from slack_mcp_server.slack_client import SlackClientManager


def resolve_dest_dir(subdir: str | None):
    if not subdir:
        return DEFAULT_DOWNLOAD_DIR
    target = (DEFAULT_DOWNLOAD_DIR / subdir).resolve()
    if not target.is_relative_to(DEFAULT_DOWNLOAD_DIR.resolve()):
        raise FileDownloadError(f"subdir must stay inside {DEFAULT_DOWNLOAD_DIR}")
    return target


def register_file_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_file(
        ctx: Context,
        file_id: str,
        subdir: str | None = None,
    ) -> str:
        """Download a file shared in Slack into ~/Downloads/slack-mcp and return its path.

        Text files (markdown, plain text, csv, json, yaml, code) also have their
        first 64 KB returned inline. File ids appear in message listings as
        [file: name (F0123..., mimetype, size)]. Files stored outside Slack
        (Google Drive, Dropbox) and native Slack documents (canvas, posts) are
        not downloaded; their link is returned instead. Requires the files:read
        user scope.

        Args:
            file_id: Slack file id (starts with F).
            subdir: Optional subdirectory of ~/Downloads/slack-mcp to save into.
        """
        app_ctx = ctx.request_context.lifespan_context
        manager = SlackClientManager(app_ctx["token_store"], app_ctx["config"])
        client = await manager.get_client()

        try:
            downloaded = await download_file(client, file_id, resolve_dest_dir(subdir))
        except FileDownloadError as exc:
            return f"Could not download {file_id}: {exc}"

        header = (
            f"Saved {downloaded.name} ({downloaded.mimetype}, {downloaded.size} bytes) "
            f"to {downloaded.path}"
        )
        if downloaded.text is None:
            return header
        if downloaded.truncated:
            header += f"\n(Showing the first {INLINE_TEXT_LIMIT_BYTES} bytes; the full file is on disk.)"
        return f"{header}\n\n{downloaded.text}"
