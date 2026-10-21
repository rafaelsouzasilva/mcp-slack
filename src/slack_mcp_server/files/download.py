from __future__ import annotations

import asyncio
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "slack-mcp"

TEXT_EXTENSIONS = {
    ".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".log", ".xml", ".sql",
    ".py", ".kt", ".java", ".ts", ".js", ".sh",
}
NATIVE_FILETYPES = {"canvas", "quip", "post", "space", "list"}
UNAVAILABLE_MODES = {"external", "tombstone", "hidden_by_limit"}

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
INLINE_TEXT_LIMIT_BYTES = 64 * 1024
MAX_REDIRECTS = 5
CHUNK_SIZE = 64 * 1024

FILE_ID_PATTERN = re.compile(r"^F[A-Z0-9]+$")
LOGIN_PAGE_MARKERS = (b"signin", b"sign in", b"slack-login", b"<form")


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
    truncated: bool


def is_slack_host(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "slack.com" or host.endswith(".slack.com"))


def is_text_file(name: str, mimetype: str) -> bool:
    return mimetype.startswith("text/") or Path(name).suffix.lower() in TEXT_EXTENSIONS


def safe_filename(file_id: str, name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", Path(name).name).strip("._") or "file"
    return f"{file_id}-{cleaned}"


def looks_like_login_page(head: bytes) -> bool:
    lowered = head.lower()
    return any(marker in lowered for marker in LOGIN_PAGE_MARKERS)


async def fetch_to_file(
    url: str,
    token: str,
    dest: Path,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    is_allowed: Callable[[str], bool] = is_slack_host,
) -> str:
    """Stream url into dest, sending the token only to allowed hosts.

    Redirects are followed by hand so the Authorization header is reapplied,
    and only while the target stays on an allowed host. Returns the final
    response Content-Type.
    """
    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60)
    current = url

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for _ in range(MAX_REDIRECTS + 1):
                if not is_allowed(current):
                    raise FileDownloadError(
                        f"Refusing to send the Slack token to {urlparse(current).hostname}"
                    )
                async with session.get(current, headers=headers, allow_redirects=False) as response:
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise FileDownloadError("Redirect without a Location header")
                        current = urljoin(current, location)
                        continue
                    if response.status != 200:
                        raise FileDownloadError(f"Download failed with HTTP {response.status}")
                    await stream_body(response, dest, max_bytes)
                    return response.headers.get("Content-Type", "")
            raise FileDownloadError(f"Too many redirects (more than {MAX_REDIRECTS})")
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise FileDownloadError(f"Network error while downloading: {exc!r}") from exc


async def stream_body(response: aiohttp.ClientResponse, dest: Path, max_bytes: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=".partial-")
    written = 0
    try:
        with os.fdopen(fd, "wb") as out:
            async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise FileDownloadError(f"File is larger than the {max_bytes} byte limit")
                out.write(chunk)
        os.replace(tmp_name, dest)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


async def get_file_info(client: AsyncWebClient, file_id: str) -> dict:
    try:
        info = await client.files_info(file=file_id)
    except SlackApiError as exc:
        error = exc.response.get("error", "unknown_error")
        if error == "missing_scope":
            raise FileDownloadError(
                "The token is missing the files:read scope: add it to the Slack app's "
                "User Token Scopes and re-authenticate."
            ) from exc
        raise FileDownloadError(f"Slack API error: {error}") from exc
    return info.get("file") or {}


async def download_file(
    client: AsyncWebClient,
    file_id: str,
    dest_dir: Path = DEFAULT_DOWNLOAD_DIR,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> DownloadedFile:
    if not FILE_ID_PATTERN.match(file_id):
        raise FileDownloadError(f"Invalid Slack file id: {file_id!r}")

    file = await get_file_info(client, file_id)
    resolved_id = file.get("id") or file_id
    name = file.get("name") or file.get("title") or resolved_id
    mimetype = file.get("mimetype", "")

    if file.get("is_external") or file.get("mode") in UNAVAILABLE_MODES:
        link = file.get("permalink") or file.get("url_private") or ""
        raise FileDownloadError(f"File is not stored in Slack (mode {file.get('mode')}); open it at {link}")
    if file.get("filetype") in NATIVE_FILETYPES:
        raise FileDownloadError(
            f"{file.get('filetype')} is a native Slack document and cannot be downloaded as a file; "
            f"open it at {file.get('permalink', '')}"
        )

    size = file.get("size")
    if isinstance(size, int) and size > max_bytes:
        raise FileDownloadError(f"File has {size} bytes, above the {max_bytes} byte limit")

    url = file.get("url_private_download") or file.get("url_private")
    if not url:
        raise FileDownloadError(f"File {resolved_id} has no downloadable content")

    path = dest_dir / safe_filename(resolved_id, name)
    content_type = await fetch_to_file(url, client.token or "", path, max_bytes)

    with path.open("rb") as handle:
        head = handle.read(INLINE_TEXT_LIMIT_BYTES)
    if content_type.startswith("text/html") and (
        not mimetype.startswith("text/html") or looks_like_login_page(head)
    ):
        path.unlink(missing_ok=True)
        raise FileDownloadError(
            "Slack returned an HTML page instead of the file (session or permission problem)"
        )

    actual_size = path.stat().st_size
    text = None
    truncated = False
    if is_text_file(name, mimetype):
        text = head.decode("utf-8", errors="replace")
        truncated = actual_size > INLINE_TEXT_LIMIT_BYTES

    return DownloadedFile(
        file_id=resolved_id,
        name=name,
        mimetype=mimetype,
        size=actual_size,
        path=path,
        text=text,
        truncated=truncated,
    )
