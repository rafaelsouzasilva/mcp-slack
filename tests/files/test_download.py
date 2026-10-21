from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from slack_mcp_server.files import download as download_module
from slack_mcp_server.files.download import (
    INLINE_TEXT_LIMIT_BYTES,
    FileDownloadError,
    download_file,
    fetch_to_file,
    is_slack_host,
    safe_filename,
)


def file_info(**overrides: object) -> dict:
    file = {
        "id": "F1",
        "name": "vision.md",
        "mimetype": "text/markdown",
        "size": 9,
        "url_private_download": "https://files.slack.com/F1/download",
        "permalink": "https://example.slack.com/files/U1/F1/vision.md",
    }
    file.update(overrides)
    return {"ok": True, "file": file}


def fake_fetch(body: bytes, content_type: str) -> AsyncMock:
    async def write(url: str, token: str, dest: Path, max_bytes: int) -> str:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return content_type

    return AsyncMock(side_effect=write)


def local_only(url: str) -> bool:
    return urlparse(url).hostname == "127.0.0.1"


@pytest.fixture
async def server() -> TestServer:
    received: list[str | None] = []

    async def file_handler(request: web.Request) -> web.Response:
        received.append(request.headers.get("Authorization"))
        return web.Response(body=b"payload", content_type="text/plain")

    async def redirect_same_host(request: web.Request) -> web.Response:
        raise web.HTTPFound("/file")

    async def redirect_other_host(request: web.Request) -> web.Response:
        raise web.HTTPFound("https://evil.example.com/steal")

    async def big(request: web.Request) -> web.Response:
        return web.Response(body=b"x" * 2048, content_type="application/octet-stream")

    async def not_found(request: web.Request) -> web.Response:
        return web.Response(status=404)

    app = web.Application()
    app.router.add_get("/file", file_handler)
    app.router.add_get("/redirect-same", redirect_same_host)
    app.router.add_get("/redirect-other", redirect_other_host)
    app.router.add_get("/big", big)
    app.router.add_get("/missing", not_found)
    test_server = TestServer(app, host="127.0.0.1")
    await test_server.start_server()
    test_server.received = received  # type: ignore[attr-defined]
    yield test_server  # type: ignore[misc]
    await test_server.close()


async def test_fetch_sends_the_token_and_writes_the_body(server: TestServer, tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"

    content_type = await fetch_to_file(str(server.make_url("/file")), "xoxp-test", dest, is_allowed=local_only)

    assert dest.read_bytes() == b"payload"
    assert content_type.startswith("text/plain")
    assert server.received == ["Bearer xoxp-test"]  # type: ignore[attr-defined]


async def test_fetch_reapplies_the_token_on_a_same_host_redirect(server: TestServer, tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"

    await fetch_to_file(str(server.make_url("/redirect-same")), "xoxp-test", dest, is_allowed=local_only)

    assert dest.read_bytes() == b"payload"
    assert server.received == ["Bearer xoxp-test"]  # type: ignore[attr-defined]


async def test_fetch_refuses_to_follow_a_redirect_to_another_host(server: TestServer, tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"

    with pytest.raises(FileDownloadError, match="evil.example.com"):
        await fetch_to_file(str(server.make_url("/redirect-other")), "xoxp-test", dest, is_allowed=local_only)

    assert not dest.exists()


async def test_fetch_aborts_above_the_size_limit_without_leaving_files(server: TestServer, tmp_path: Path) -> None:
    dest = tmp_path / "out.bin"

    with pytest.raises(FileDownloadError, match="1024 byte limit"):
        await fetch_to_file(str(server.make_url("/big")), "xoxp-test", dest, max_bytes=1024, is_allowed=local_only)

    assert list(tmp_path.iterdir()) == []


async def test_fetch_reports_a_non_200_status(server: TestServer, tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="HTTP 404"):
        await fetch_to_file(str(server.make_url("/missing")), "xoxp-test", tmp_path / "out", is_allowed=local_only)


async def test_fetch_refuses_a_non_slack_url_by_default(tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="drive.google.com"):
        await fetch_to_file("https://drive.google.com/file/d/abc", "xoxp-test", tmp_path / "out")


def test_is_slack_host() -> None:
    assert is_slack_host("https://files.slack.com/files-pri/T1-F1/download/x.md")
    assert is_slack_host("https://slack.com/x")
    assert not is_slack_host("http://files.slack.com/x")
    assert not is_slack_host("https://files.slack.com.evil.com/x")
    assert not is_slack_host("https://docs.google.com/x")


async def test_text_file_is_saved_and_returned_inline(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    fetch = fake_fetch(b"# Vision\n", "text/markdown")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info())), \
            patch.object(download_module, "fetch_to_file", fetch):
        result = await download_file(client, "F1", tmp_path)

    assert result.path == tmp_path / "F1-vision.md"
    assert result.path.read_bytes() == b"# Vision\n"
    assert result.text == "# Vision\n"
    assert result.truncated is False
    assert fetch.await_args.args[:2] == ("https://files.slack.com/F1/download", "xoxp-test")


async def test_large_text_file_is_truncated_inline_but_complete_on_disk(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    body = b"a" * (INLINE_TEXT_LIMIT_BYTES + 10)
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info(size=len(body)))), \
            patch.object(download_module, "fetch_to_file", fake_fetch(body, "text/markdown")):
        result = await download_file(client, "F1", tmp_path)

    assert result.size == len(body)
    assert result.truncated is True
    assert result.text == "a" * INLINE_TEXT_LIMIT_BYTES


async def test_binary_file_is_saved_without_inline_text(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    info = file_info(name="shot.png", mimetype="image/png")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=info)), \
            patch.object(download_module, "fetch_to_file", fake_fetch(b"\x89PNG", "image/png")):
        result = await download_file(client, "F1", tmp_path)

    assert result.path.read_bytes() == b"\x89PNG"
    assert result.text is None


async def test_html_instead_of_the_file_is_reported_and_removed(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info())), \
            patch.object(download_module, "fetch_to_file", fake_fetch(b"<html>", "text/html; charset=utf-8")):
        with pytest.raises(FileDownloadError, match="HTML page"):
            await download_file(client, "F1", tmp_path)

    assert list(tmp_path.iterdir()) == []


async def test_login_page_is_rejected_even_for_an_html_file(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    info = file_info(name="page.html", mimetype="text/html")
    login = b"<html><form action='/signin'>Sign in to Slack</form></html>"
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=info)), \
            patch.object(download_module, "fetch_to_file", fake_fetch(login, "text/html")):
        with pytest.raises(FileDownloadError, match="HTML page"):
            await download_file(client, "F1", tmp_path)


async def test_external_file_is_not_downloaded(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    info = file_info(is_external=True, mode="external", url_private="https://docs.google.com/doc")
    fetch = fake_fetch(b"", "")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=info)), \
            patch.object(download_module, "fetch_to_file", fetch):
        with pytest.raises(FileDownloadError, match="not stored in Slack"):
            await download_file(client, "F1", tmp_path)

    fetch.assert_not_awaited()


async def test_native_slack_document_is_not_downloaded(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    fetch = fake_fetch(b"", "")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info(filetype="canvas"))), \
            patch.object(download_module, "fetch_to_file", fetch):
        with pytest.raises(FileDownloadError, match="native Slack document"):
            await download_file(client, "F1", tmp_path)

    fetch.assert_not_awaited()


async def test_file_above_the_limit_is_refused_before_downloading(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    fetch = fake_fetch(b"", "")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info(size=5000))), \
            patch.object(download_module, "fetch_to_file", fetch):
        with pytest.raises(FileDownloadError, match="5000 bytes"):
            await download_file(client, "F1", tmp_path, max_bytes=1000)

    fetch.assert_not_awaited()


async def test_missing_scope_is_explained(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    error = SlackApiError("missing_scope", {"ok": False, "error": "missing_scope"})
    with patch.object(AsyncWebClient, "files_info", AsyncMock(side_effect=error)):
        with pytest.raises(FileDownloadError, match="files:read"):
            await download_file(client, "F1", tmp_path)


async def test_other_api_errors_are_reported_by_code(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    error = SlackApiError("file_not_found", {"ok": False, "error": "file_not_found"})
    with patch.object(AsyncWebClient, "files_info", AsyncMock(side_effect=error)):
        with pytest.raises(FileDownloadError, match="file_not_found"):
            await download_file(client, "F1", tmp_path)


async def test_invalid_file_id_is_rejected_before_calling_slack(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    info = AsyncMock(return_value=file_info())
    with patch.object(AsyncWebClient, "files_info", info):
        with pytest.raises(FileDownloadError, match="Invalid Slack file id"):
            await download_file(client, "../../etc", tmp_path)

    info.assert_not_awaited()


def test_safe_filename_strips_path_and_odd_characters() -> None:
    assert safe_filename("F1", "../etc/passwd") == "F1-passwd"
    assert safe_filename("F1", "my vision doc.md") == "F1-my_vision_doc.md"
