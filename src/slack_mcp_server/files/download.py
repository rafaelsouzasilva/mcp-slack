from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from slack_sdk.web.async_client import AsyncWebClient

DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "slack-mcp"

TEXT_EXTENSIONS = {
    ".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".log", ".xml", ".sql",
    ".py", ".kt", ".java", ".ts", ".js", ".sh",
}
INLINE_TEXT_LIMIT_BYTES = 512 * 1024


class FileDownloadError(Exception):
    pass


@dataclass
class DownloadedFile:
    file_id: str
    name: str
    mimetype: str
    size: int
    path: Path
    text: str | None


def is_text_file(name: str, mimetype: str) -> bool:
    return mimetype.startswith("text/") or Path(name).suffix.lower() in TEXT_EXTENSIONS


def safe_filename(file_id: str, name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", Path(name).name).strip("._") or "file"
    return f"{file_id}-{cleaned}"


async def fetch_bytes(url: str, token: str) -> tuple[bytes, str]:
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise FileDownloadError(f"Download failed with HTTP {response.status}")
            return await response.read(), response.headers.get("Content-Type", "")


async def download_file(
    client: AsyncWebClient,
    file_id: str,
    dest_dir: Path = DEFAULT_DOWNLOAD_DIR,
) -> DownloadedFile:
    info = await client.files_info(file=file_id)
    file = info.get("file") or {}
    url = file.get("url_private_download") or file.get("url_private")
    if not url:
        raise FileDownloadError(f"File {file_id} has no downloadable content")

    name = file.get("name") or file.get("title") or file_id
    mimetype = file.get("mimetype", "")

    content, content_type = await fetch_bytes(url, client.token or "")
    if content_type.startswith("text/html") and not mimetype.startswith("text/html"):
        raise FileDownloadError(
            "Slack returned an HTML page instead of the file. "
            "The token is probably missing the files:read scope: add it to the "
            "Slack app's User Token Scopes and re-authenticate."
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / safe_filename(file_id, name)
    path.write_bytes(content)

    text = None
    if is_text_file(name, mimetype) and len(content) <= INLINE_TEXT_LIMIT_BYTES:
        text = content.decode("utf-8", errors="replace")

    return DownloadedFile(
        file_id=file_id,
        name=name,
        mimetype=mimetype,
        size=len(content),
        path=path,
        text=text,
    )
