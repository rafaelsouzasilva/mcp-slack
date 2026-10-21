from __future__ import annotations

import asyncio
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

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
DOWNLOAD_DEADLINE_SECONDS = 300.0
MAX_REDIRECTS = 5
CHUNK_SIZE = 64 * 1024
REDIRECT_STATUSES = {301, 302, 303, 307, 308}

FILE_ID_PATTERN = re.compile(r"F[A-Z0-9]+")


class FileDownloadError(Exception):
    pass


@dataclass
class FetchResult:
    temp_path: Path
    content_type: str
    final_url: str


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


def is_valid_file_id(file_id: str) -> bool:
    return FILE_ID_PATTERN.fullmatch(file_id) is not None


def is_text_file(name: str, mimetype: str) -> bool:
    return mimetype.startswith("text/") or Path(name).suffix.lower() in TEXT_EXTENSIONS


def safe_filename(file_id: str, name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", Path(name).name).strip("._") or "file"
    return f"{file_id}-{cleaned}"


def landed_on_sign_in(final_url: str) -> bool:
    parsed = urlparse(final_url)
    if "redir" in {key.lower() for key in parse_qs(parsed.query)}:
        return True
    if (parsed.hostname or "").lower() == "files.slack.com":
        return False
    segments = [segment.lower() for segment in parsed.path.split("/") if segment]
    return "signin" in segments


async def fetch_to_file(
    url: str,
    token: str,
    dest_dir: Path,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    is_allowed: Callable[[str], bool] | None = None,
    deadline_seconds: float = DOWNLOAD_DEADLINE_SECONDS,
) -> FetchResult:
    """Stream url into a temporary file in dest_dir, sending the token only to allowed hosts.

    Redirects are followed by hand so the Authorization header is reapplied,
    and only while the target stays on an allowed host. The caller decides
    whether to promote or discard the temporary file.
    """
    allowed = is_allowed or is_slack_host
    try:
        return await asyncio.wait_for(
            _fetch(url, token, dest_dir, max_bytes, allowed), timeout=deadline_seconds
        )
    except aiohttp.ServerTimeoutError as exc:
        raise FileDownloadError(f"Connection to Slack timed out: {exc!r}") from exc
    except asyncio.TimeoutError as exc:
        raise FileDownloadError(f"Download did not finish within {deadline_seconds:g} seconds") from exc
    except aiohttp.ClientError as exc:
        raise FileDownloadError(f"Network error while downloading: {exc!r}") from exc
    except OSError as exc:
        raise FileDownloadError(f"Could not write the file: {exc}") from exc


async def _fetch(
    url: str,
    token: str,
    dest_dir: Path,
    max_bytes: int,
    allowed: Callable[[str], bool],
) -> FetchResult:
    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=60)
    current = url
    temp_path: Path | None = None

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for _ in range(MAX_REDIRECTS + 1):
                if not allowed(current):
                    raise FileDownloadError(
                        f"Refusing to send the Slack token to {urlparse(current).hostname}"
                    )
                async with session.get(current, headers=headers, allow_redirects=False) as response:
                    if response.status in REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            raise FileDownloadError("Redirect without a Location header")
                        current = urljoin(current, location)
                        continue
                    if response.status != 200:
                        raise FileDownloadError(f"Download failed with HTTP {response.status}")
                    temp_path = await stream_body(response, dest_dir, max_bytes)
                    result = FetchResult(
                        temp_path=temp_path,
                        content_type=response.headers.get("Content-Type", ""),
                        final_url=current,
                    )
                return result
            raise FileDownloadError(f"Too many redirects (more than {MAX_REDIRECTS})")
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


async def stream_body(response: aiohttp.ClientResponse, dest_dir: Path, max_bytes: int) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest_dir, prefix=".partial-")
    temp_path = Path(tmp_name)
    written = 0
    try:
        with os.fdopen(fd, "wb") as out:
            async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise FileDownloadError(f"File is larger than the {max_bytes} byte limit")
                out.write(chunk)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


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
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise FileDownloadError(f"Network error while calling files.info: {exc!r}") from exc
    return info.get("file") or {}


def is_unexpected_html(content_type: str, mimetype: str, final_url: str) -> bool:
    if not content_type.startswith("text/html"):
        return False
    return not mimetype.startswith("text/html") or landed_on_sign_in(final_url)


async def download_file(
    client: AsyncWebClient,
    file_id: str,
    dest_dir: Path = DEFAULT_DOWNLOAD_DIR,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> DownloadedFile:
    if not is_valid_file_id(file_id):
        raise FileDownloadError(f"Invalid Slack file id: {file_id!r}")

    file = await get_file_info(client, file_id)
    response_id = file.get("id")
    resolved_id = response_id if isinstance(response_id, str) and is_valid_file_id(response_id) else file_id
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

    fetched = await fetch_to_file(url, client.token or "", dest_dir, max_bytes)
    try:
        if is_unexpected_html(fetched.content_type, mimetype, fetched.final_url):
            raise FileDownloadError(
                "Slack returned an HTML page instead of the file (session or permission problem)"
            )
        path = dest_dir / safe_filename(resolved_id, name)
        os.replace(fetched.temp_path, path)
    except OSError as exc:
        fetched.temp_path.unlink(missing_ok=True)
        raise FileDownloadError(f"Could not write the file: {exc}") from exc
    except BaseException:
        fetched.temp_path.unlink(missing_ok=True)
        raise

    text = None
    truncated = False
    try:
        actual_size = path.stat().st_size
        if is_text_file(name, mimetype):
            with path.open("rb") as handle:
                head = handle.read(INLINE_TEXT_LIMIT_BYTES)
            text = head.decode("utf-8", errors="replace")
            truncated = actual_size > INLINE_TEXT_LIMIT_BYTES
    except OSError as exc:
        raise FileDownloadError(f"Saved to {path} but could not read it back: {exc}") from exc

    return DownloadedFile(
        file_id=resolved_id,
        name=name,
        mimetype=mimetype,
        size=actual_size,
        path=path,
        text=text,
        truncated=truncated,
    )
