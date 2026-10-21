from __future__ import annotations


def format_file(file: dict) -> str:
    name = file.get("name") or file.get("title") or "unnamed"
    file_id = file.get("id", "")
    mimetype = file.get("mimetype", "unknown")
    size = file.get("size")
    size_part = f", {size} bytes" if size is not None else ""
    return f"[file: {name} ({file_id}, {mimetype}{size_part})]"


def format_message(msg: dict) -> str:
    user = msg.get("user", "unknown")
    text = msg.get("text", "")
    ts = msg.get("ts", "")
    line = f"[{ts}] <{user}> {text}".rstrip()

    files = msg.get("files") or []
    if files:
        line += " " + " ".join(format_file(f) for f in files)

    if msg.get("reply_count"):
        line += f" [thread: {msg['reply_count']} replies]"

    return line
