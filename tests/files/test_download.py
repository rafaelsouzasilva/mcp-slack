from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from slack_sdk.web.async_client import AsyncWebClient

from slack_mcp_server.files import download as download_module
from slack_mcp_server.files.download import FileDownloadError, download_file, safe_filename


def file_info(name: str, mimetype: str) -> dict:
    return {
        "ok": True,
        "file": {
            "id": "F1",
            "name": name,
            "mimetype": mimetype,
            "url_private_download": "https://files.slack.com/F1/download",
        },
    }


async def test_text_file_is_saved_and_returned_inline(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    fetch = AsyncMock(return_value=(b"# Vision\n", "text/markdown"))
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info("vision.md", "text/markdown"))), \
            patch.object(download_module, "fetch_bytes", fetch):
        result = await download_file(client, "F1", tmp_path)

    assert result.path == tmp_path / "F1-vision.md"
    assert result.path.read_bytes() == b"# Vision\n"
    assert result.text == "# Vision\n"
    assert result.size == 9
    fetch.assert_awaited_once_with("https://files.slack.com/F1/download", "xoxp-test")


async def test_binary_file_is_saved_without_inline_text(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info("shot.png", "image/png"))), \
            patch.object(download_module, "fetch_bytes", AsyncMock(return_value=(b"\x89PNG", "image/png"))):
        result = await download_file(client, "F1", tmp_path)

    assert result.path.read_bytes() == b"\x89PNG"
    assert result.text is None


async def test_html_login_page_reports_missing_scope(tmp_path: Path) -> None:
    client = AsyncWebClient(token="xoxp-test")
    with patch.object(AsyncWebClient, "files_info", AsyncMock(return_value=file_info("vision.md", "text/markdown"))), \
            patch.object(download_module, "fetch_bytes", AsyncMock(return_value=(b"<html>", "text/html; charset=utf-8"))):
        with pytest.raises(FileDownloadError, match="files:read"):
            await download_file(client, "F1", tmp_path)

    assert not any(tmp_path.iterdir())


def test_safe_filename_strips_path_and_odd_characters() -> None:
    assert safe_filename("F1", "../etc/passwd") == "F1-passwd"
    assert safe_filename("F1", "my vision doc.md") == "F1-my_vision_doc.md"
