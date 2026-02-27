from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth redirect callback."""

    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)

        if "error" in params:
            _CallbackHandler.error = params["error"][0]
            self._respond("Authentication failed. You can close this tab.")
        elif "code" in params:
            _CallbackHandler.code = params["code"][0]
            _CallbackHandler.state = params.get("state", [None])[0]
            self._respond(
                "Authentication successful! You can close this tab and return to Claude Code."
            )
        else:
            self._respond("Missing code parameter.", status=400)

        self.server._ready_event.set()  # type: ignore[attr-defined]

    def _respond(self, message: str, status: int = 200) -> None:
        html = f"""<!DOCTYPE html>
<html><head><title>Slack MCP Auth</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px">
<h2>{message}</h2>
</body></html>"""
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress HTTP logs


class OAuthCallbackServer:
    """Temporary HTTP server that waits for the OAuth callback."""

    def __init__(self, port: int = 9876) -> None:
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None
        self._ready = asyncio.Event()

    async def wait_for_callback(self, timeout: float = 300) -> dict[str, str | None]:
        _CallbackHandler.code = None
        _CallbackHandler.state = None
        _CallbackHandler.error = None

        self._server = HTTPServer(("127.0.0.1", self._port), _CallbackHandler)
        self._server._ready_event = asyncio.Event()  # type: ignore[attr-defined]

        loop = asyncio.get_running_loop()
        threading_event = asyncio.Event()

        # Bridge threading event to asyncio
        server_ready = self._server._ready_event  # type: ignore[attr-defined]

        def _serve() -> None:
            while not server_ready.is_set():
                self._server.handle_request()  # type: ignore[union-attr]
            loop.call_soon_threadsafe(threading_event.set)

        self._thread = Thread(target=_serve, daemon=True)
        self._thread.start()

        try:
            await asyncio.wait_for(threading_event.wait(), timeout=timeout)
        except TimeoutError:
            return {"error": "OAuth callback timed out"}
        finally:
            if self._server:
                self._server.server_close()

        if _CallbackHandler.error:
            return {"error": _CallbackHandler.error}

        return {
            "code": _CallbackHandler.code,
            "state": _CallbackHandler.state,
        }
