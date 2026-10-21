from __future__ import annotations

import pytest

from slack_mcp_server.files.download import DEFAULT_DOWNLOAD_DIR, FileDownloadError
from slack_mcp_server.files.tools import resolve_dest_dir


def test_default_destination() -> None:
    assert resolve_dest_dir(None) == DEFAULT_DOWNLOAD_DIR


def test_subdir_stays_inside_the_download_dir() -> None:
    assert resolve_dest_dir("threads") == (DEFAULT_DOWNLOAD_DIR / "threads").resolve()


@pytest.mark.parametrize("subdir", ["../../.ssh", "/etc", "a/../../.."])
def test_subdir_cannot_escape_the_download_dir(subdir: str) -> None:
    with pytest.raises(FileDownloadError, match="inside"):
        resolve_dest_dir(subdir)
