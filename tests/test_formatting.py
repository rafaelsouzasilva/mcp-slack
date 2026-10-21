from __future__ import annotations

from slack_mcp_server.formatting import format_file, format_message


def test_format_message_plain() -> None:
    assert format_message({"user": "U1", "text": "hi", "ts": "1.1"}) == "[1.1] <U1> hi"


def test_format_message_with_files_and_empty_text() -> None:
    msg = {
        "user": "U1",
        "text": "",
        "ts": "1.2",
        "reply_count": 1,
        "files": [
            {"id": "F1", "name": "vision.md", "mimetype": "text/markdown", "size": 42},
        ],
    }
    assert format_message(msg) == (
        "[1.2] <U1> [file: vision.md (F1, text/markdown, 42 bytes)] [thread: 1 replies]"
    )


def test_format_file_without_size_or_name() -> None:
    assert format_file({"id": "F2", "title": "Screenshot", "mimetype": "image/png"}) == (
        "[file: Screenshot (F2, image/png)]"
    )
