from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import aiohttp
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
    is_valid_file_id,
    safe_filename,
)

LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def local_only(url: str) -> bool:
    return urlparse(url).hostname in LOCAL_HOSTS


def file_info(url: str = "https://files.slack.com/F1/download", **overrides: object) -> dict:
    file = {
        "id": "F1",
        "name": "vision.md",
        "mimetype": "text/markdown",
        "size": 9,
        "url_private_download": url,
        "permalink": "https://example.slack.com/files/U1/F1/vision.md",
    }
    file.update(overrides)
    return {"ok": True, "file": file}


@pytest.fixture
async def server() -> TestServer:
    received: list[str | None] = []
    streaming = asyncio.Event()

    async def file_handler(request: web.Request) -> web.Response:
        received.append(request.headers.get("Authorization"))
        return web.Response(body=b"payload", content_type="text/plain")

    async def markdown(request: web.Request) -> web.Response:
        return web.Response(body=b"# Vision\n", content_type="text/markdown")

    async def legit_html(request: web.Request) -> web.Response:
        body = b"<html><body><h1>Designing the onboarding</h1><form>sign in</form></body></html>"
        return web.Response(body=body, content_type="text/html")

    async def html_instead(request: web.Request) -> web.Response:
        return web.Response(body=b"<html>oops</html>", content_type="text/html")

    async def to_signin(request: web.Request) -> web.Response:
        raise web.HTTPFound("/signin?redir=%2Ffiles%2FF1")

    async def signin(request: web.Request) -> web.Response:
        return web.Response(body=b"<html>Sign in</html>", content_type="text/html")

    async def redirect_other_allowed_host(request: web.Request) -> web.Response:
        raise web.HTTPFound(f"http://localhost:{request.url.port}/file")

    async def redirect_disallowed_host(request: web.Request) -> web.Response:
        raise web.HTTPFound("https://evil.example.com/steal")

    async def redirect_without_location(request: web.Request) -> web.Response:
        return web.Response(status=302)

    async def redirect_loop(request: web.Request) -> web.Response:
        raise web.HTTPFound("/loop")

    async def big(request: web.Request) -> web.Response:
        return web.Response(body=b"x" * 2048, content_type="application/octet-stream")

    async def stall(request: web.Request) -> web.Response:
        await asyncio.sleep(5)
        return web.Response(body=b"late")

    async def signin_named_file(request: web.Request) -> web.Response:
        return web.Response(body=b"<html><h1>Signin flow</h1></html>", content_type="text/html")

    async def not_found(request: web.Request) -> web.Response:
        return web.Response(status=404)

    async def trickle(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        await response.prepare(request)
        for _ in range(50):
            await response.write(b"x")
            streaming.set()
            await asyncio.sleep(0.1)
        return response

    app = web.Application()
    app.router.add_get("/file", file_handler)
    app.router.add_get("/vision.md", markdown)
    app.router.add_get("/legit.html", legit_html)
    app.router.add_get("/html-instead", html_instead)
    app.router.add_get("/to-signin", to_signin)
    app.router.add_get("/signin", signin)
    app.router.add_get("/redirect-other-allowed", redirect_other_allowed_host)
    app.router.add_get("/redirect-disallowed", redirect_disallowed_host)
    app.router.add_get("/redirect-no-location", redirect_without_location)
    app.router.add_get("/loop", redirect_loop)
    app.router.add_get("/big", big)
    app.router.add_get("/missing", not_found)
    app.router.add_get("/download/signin-flow.html", signin_named_file)
    app.router.add_get("/stall", stall)
    app.router.add_get("/trickle", trickle)
    test_server = TestServer(app, host="127.0.0.1")
    await test_server.start_server()
    test_server.received = received  # type: ignore[attr-defined]
    test_server.streaming = streaming  # type: ignore[attr-defined]
    yield test_server  # type: ignore[misc]
    await test_server.close()


def url(server: TestServer, path: str) -> str:
    return str(server.make_url(path))


async def fetch(server: TestServer, path: str, dest_dir: Path, **kwargs: object):
    return await fetch_to_file(url(server, path), "xoxp-test", dest_dir, is_allowed=local_only, **kwargs)


async def test_fetch_sends_the_token_and_streams_into_a_temporary_file(server: TestServer, tmp_path: Path) -> None:
    result = await fetch(server, "/file", tmp_path)

    assert result.temp_path.parent == tmp_path
    assert result.temp_path.name.startswith(".partial-")
    assert result.temp_path.read_bytes() == b"payload"
    assert result.content_type.startswith("text/plain")
    assert server.received == ["Bearer xoxp-test"]  # type: ignore[attr-defined]


async def test_fetch_reapplies_the_token_on_a_redirect_to_another_allowed_host(
    server: TestServer, tmp_path: Path
) -> None:
    result = await fetch(server, "/redirect-other-allowed", tmp_path)

    assert result.temp_path.read_bytes() == b"payload"
    assert urlparse(result.final_url).hostname == "localhost"
    assert server.received == ["Bearer xoxp-test"]  # type: ignore[attr-defined]


async def test_fetch_refuses_to_follow_a_redirect_to_a_disallowed_host(server: TestServer, tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="evil.example.com"):
        await fetch(server, "/redirect-disallowed", tmp_path)

    assert list(tmp_path.iterdir()) == []


async def test_fetch_reports_a_redirect_without_location(server: TestServer, tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="Location"):
        await fetch(server, "/redirect-no-location", tmp_path)


async def test_fetch_stops_a_redirect_loop(server: TestServer, tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="Too many redirects"):
        await fetch(server, "/loop", tmp_path)


async def test_fetch_aborts_above_the_size_limit_without_leaving_files(server: TestServer, tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="1024 byte limit"):
        await fetch(server, "/big", tmp_path, max_bytes=1024)

    assert list(tmp_path.iterdir()) == []


async def test_fetch_reports_a_non_200_status(server: TestServer, tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="HTTP 404"):
        await fetch(server, "/missing", tmp_path)


async def test_fetch_gives_up_on_a_trickling_download_and_cleans_up(server: TestServer, tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="did not finish within 0.5 seconds"):
        await fetch(server, "/trickle", tmp_path, deadline_seconds=0.5)

    assert list(tmp_path.iterdir()) == []


async def test_fetch_cleans_up_when_cancelled(server: TestServer, tmp_path: Path) -> None:
    task = asyncio.create_task(fetch(server, "/trickle", tmp_path))
    await asyncio.wait_for(server.streaming.wait(), timeout=5)  # type: ignore[attr-defined]
    await asyncio.sleep(0.05)
    assert [p.name.startswith(".partial-") for p in tmp_path.iterdir()] == [True]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert list(tmp_path.iterdir()) == []


async def test_fetch_removes_the_temp_file_when_cancelled_while_the_session_closes(
    server: TestServer, tmp_path: Path
) -> None:
    async def cancelled_exit(self, *exc_info):
        raise asyncio.CancelledError()

    with patch.object(aiohttp.ClientSession, "__aexit__", cancelled_exit):
        with pytest.raises(asyncio.CancelledError):
            await fetch(server, "/file", tmp_path)

    assert list(tmp_path.iterdir()) == []


async def test_fetch_removes_the_temp_file_when_the_deadline_hits_while_the_session_closes(
    server: TestServer, tmp_path: Path
) -> None:
    async def slow_exit(self, *exc_info):
        await asyncio.sleep(5)

    with patch.object(aiohttp.ClientSession, "__aexit__", slow_exit):
        with pytest.raises(FileDownloadError, match="did not finish"):
            await fetch(server, "/file", tmp_path, deadline_seconds=0.5)

    assert list(tmp_path.iterdir()) == []


async def test_fetch_reports_a_stalled_read_as_a_connection_timeout(server: TestServer, tmp_path: Path) -> None:
    timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=0.3)
    with patch.object(download_module.aiohttp, "ClientTimeout", return_value=timeout):
        with pytest.raises(FileDownloadError, match="Connection to Slack timed out"):
            await fetch(server, "/stall", tmp_path)

    assert list(tmp_path.iterdir()) == []


async def test_fetch_reports_a_destination_that_cannot_be_created(server: TestServer, tmp_path: Path) -> None:
    blocker = tmp_path / "taken"
    blocker.write_text("a file, not a directory")

    with pytest.raises(FileDownloadError, match="Could not write the file"):
        await fetch(server, "/file", blocker / "sub")


async def test_fetch_refuses_a_non_slack_url_by_default(tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="drive.google.com"):
        await fetch_to_file("https://drive.google.com/file/d/abc", "xoxp-test", tmp_path)


def test_is_slack_host() -> None:
    assert is_slack_host("https://files.slack.com/files-pri/T1-F1/download/x.md")
    assert is_slack_host("https://slack.com/x")
    assert not is_slack_host("http://files.slack.com/x")
    assert not is_slack_host("https://files.slack.com.evil.com/x")
    assert not is_slack_host("https://docs.google.com/x")


def test_is_valid_file_id() -> None:
    assert is_valid_file_id("F0ABC123")
    assert not is_valid_file_id("F123\n")
    assert not is_valid_file_id("../../etc")
    assert not is_valid_file_id("f123")


def slack_client() -> AsyncWebClient:
    return AsyncWebClient(token="xoxp-test")


async def download_from(server: TestServer, tmp_path: Path, path: str, **info: object):
    files_info = AsyncMock(return_value=file_info(url(server, path), **info))
    with patch.object(AsyncWebClient, "files_info", files_info), \
            patch.object(download_module, "is_slack_host", local_only):
        return await download_file(slack_client(), "F1", tmp_path)


async def test_text_file_is_saved_and_returned_inline(server: TestServer, tmp_path: Path) -> None:
    result = await download_from(server, tmp_path, "/vision.md")

    assert result.path == tmp_path / "F1-vision.md"
    assert result.path.read_bytes() == b"# Vision\n"
    assert result.text == "# Vision\n"
    assert result.truncated is False
    assert list(tmp_path.iterdir()) == [result.path]


async def test_legitimate_html_file_is_accepted(server: TestServer, tmp_path: Path) -> None:
    result = await download_from(server, tmp_path, "/legit.html", name="report.html", mimetype="text/html", size=80)

    assert result.path == tmp_path / "F1-report.html"
    assert b"Designing the onboarding" in result.path.read_bytes()


async def test_html_file_with_signin_in_its_name_is_accepted(server: TestServer, tmp_path: Path) -> None:
    result = await download_from(
        server, tmp_path, "/download/signin-flow.html", name="signin-flow.html", mimetype="text/html", size=33
    )

    assert result.path == tmp_path / "F1-signin-flow.html"


def test_landed_on_sign_in() -> None:
    assert download_module.landed_on_sign_in("https://acme.slack.com/?redir=%2Ffiles-pri%2FT1-F1")
    assert download_module.landed_on_sign_in("https://acme.slack.com/signin")
    assert not download_module.landed_on_sign_in("https://acme.slack.com/files?noredir=1")
    assert not download_module.landed_on_sign_in(
        "https://files.slack.com/files-pri/T1-F1/download/signin-flow.html"
    )
    assert not download_module.landed_on_sign_in("https://files.slack.com/files-pri/T1-F1/download/signin")


async def test_html_instead_of_the_file_keeps_the_previous_copy(server: TestServer, tmp_path: Path) -> None:
    previous = tmp_path / "F1-vision.md"
    previous.write_bytes(b"good copy")

    with pytest.raises(FileDownloadError, match="HTML page"):
        await download_from(server, tmp_path, "/html-instead")

    assert previous.read_bytes() == b"good copy"
    assert list(tmp_path.iterdir()) == [previous]


async def test_sign_in_redirect_is_rejected_even_for_an_html_file(server: TestServer, tmp_path: Path) -> None:
    with pytest.raises(FileDownloadError, match="HTML page"):
        await download_from(server, tmp_path, "/to-signin", name="page.html", mimetype="text/html")

    assert list(tmp_path.iterdir()) == []


async def test_large_text_file_is_truncated_inline_but_complete_on_disk(tmp_path: Path) -> None:
    body = b"a" * (INLINE_TEXT_LIMIT_BYTES + 10)
    temp = tmp_path / ".partial-test"
    temp.write_bytes(body)
    fetched = download_module.FetchResult(temp, "text/markdown", "https://files.slack.com/F1/download")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info(size=len(body)))), \
            patch.object(download_module, "fetch_to_file", AsyncMock(return_value=fetched)):
        result = await download_file(slack_client(), "F1", tmp_path)

    assert result.size == len(body)
    assert result.path.read_bytes() == body
    assert result.truncated is True
    assert result.text == "a" * INLINE_TEXT_LIMIT_BYTES


async def test_response_id_that_is_not_a_file_id_falls_back_to_the_requested_id(
    server: TestServer, tmp_path: Path
) -> None:
    result = await download_from(server, tmp_path, "/vision.md", id="../evil")

    assert result.path == tmp_path / "F1-vision.md"


async def test_external_file_is_not_downloaded(tmp_path: Path) -> None:
    info = file_info(is_external=True, mode="external", url_private="https://docs.google.com/doc")
    fetch_mock = AsyncMock()
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=info)), \
            patch.object(download_module, "fetch_to_file", fetch_mock):
        with pytest.raises(FileDownloadError, match="not stored in Slack"):
            await download_file(slack_client(), "F1", tmp_path)

    fetch_mock.assert_not_awaited()


async def test_native_slack_document_is_not_downloaded(tmp_path: Path) -> None:
    fetch_mock = AsyncMock()
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info(filetype="canvas"))), \
            patch.object(download_module, "fetch_to_file", fetch_mock):
        with pytest.raises(FileDownloadError, match="native Slack document"):
            await download_file(slack_client(), "F1", tmp_path)

    fetch_mock.assert_not_awaited()


async def test_file_above_the_limit_is_refused_before_downloading(tmp_path: Path) -> None:
    fetch_mock = AsyncMock()
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info(size=5000))), \
            patch.object(download_module, "fetch_to_file", fetch_mock):
        with pytest.raises(FileDownloadError, match="5000 bytes"):
            await download_file(slack_client(), "F1", tmp_path, max_bytes=1000)

    fetch_mock.assert_not_awaited()


async def test_missing_scope_is_explained(tmp_path: Path) -> None:
    error = SlackApiError("missing_scope", {"ok": False, "error": "missing_scope"})
    with patch.object(AsyncWebClient, "files_info", AsyncMock(side_effect=error)):
        with pytest.raises(FileDownloadError, match="files:read"):
            await download_file(slack_client(), "F1", tmp_path)


async def test_other_api_errors_are_reported_by_code(tmp_path: Path) -> None:
    error = SlackApiError("file_not_found", {"ok": False, "error": "file_not_found"})
    with patch.object(AsyncWebClient, "files_info", AsyncMock(side_effect=error)):
        with pytest.raises(FileDownloadError, match="file_not_found"):
            await download_file(slack_client(), "F1", tmp_path)


async def test_network_error_on_files_info_is_reported(tmp_path: Path) -> None:
    with patch.object(AsyncWebClient, "files_info", AsyncMock(side_effect=asyncio.TimeoutError())):
        with pytest.raises(FileDownloadError, match="files.info"):
            await download_file(slack_client(), "F1", tmp_path)


async def test_invalid_file_id_is_rejected_before_calling_slack(tmp_path: Path) -> None:
    info = AsyncMock(return_value=file_info())
    with patch.object(AsyncWebClient, "files_info", info):
        with pytest.raises(FileDownloadError, match="Invalid Slack file id"):
            await download_file(slack_client(), "F123\n", tmp_path)

    info.assert_not_awaited()


def test_safe_filename_strips_path_and_odd_characters() -> None:
    assert safe_filename("F1", "../etc/passwd") == "F1-passwd"
    assert safe_filename("F1", "my vision doc.md") == "F1-my_vision_doc.md"
