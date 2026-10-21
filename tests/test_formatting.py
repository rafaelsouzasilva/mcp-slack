from __future__ import annotations

from slack_mcp_server.formatting import format_file, format_message, format_thread


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


def test_format_thread_keeps_the_parent_on_the_first_page() -> None:
    messages = [
        {"user": "U1", "text": "parent", "ts": "1.0", "thread_ts": "1.0"},
        {"user": "U2", "text": "reply", "ts": "1.1", "thread_ts": "1.0"},
    ]
    assert format_thread(messages, paginated=False) == "[1.0] <U1> parent\n[1.1] <U2> reply"


def test_format_thread_drops_the_repeated_parent_on_later_pages() -> None:
    messages = [
        {"user": "U1", "text": "parent", "ts": "1.0", "thread_ts": "1.0"},
        {"user": "U3", "text": "later", "ts": "1.5", "thread_ts": "1.0"},
    ]
    assert format_thread(messages, paginated=True) == "[1.5] <U3> later"


def test_format_thread_keeps_a_reply_that_opens_a_later_page() -> None:
    messages = [{"user": "U3", "text": "later", "ts": "1.5", "thread_ts": "1.0"}]
    assert format_thread(messages, paginated=True) == "[1.5] <U3> later"
