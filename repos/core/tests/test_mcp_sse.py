from __future__ import annotations

import json
import secrets
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from layoutsee_core.bootstrap import build_core
from layoutsee_core.server import McpSseHub


class McpSseTest(unittest.TestCase):
    """MCP over SSE：会话注册表、直连兜底、按 sessionId 回推。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-mcp-")
        self.nonce = secrets.token_hex(32)
        self.context, self.server = build_core(self.nonce, data_dir=Path(self.temp.name), port_start=33540)
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.base_port = self.server.server_port

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _post(self, path: str, payload: dict) -> tuple[int, object]:
        connection = HTTPConnection("127.0.0.1", self.base_port, timeout=5)
        try:
            connection.request("POST", path, body=json.dumps(payload), headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else None)
        finally:
            connection.close()

    def test_hub_open_get_close(self) -> None:
        hub = McpSseHub()
        session = hub.open("android-x")
        self.assertIs(hub.get(session.session_id), session)
        hub.close(session.session_id)
        self.assertIsNone(hub.get(session.session_id))

    def test_direct_initialize_returns_body(self) -> None:
        status, payload = self._post("/mcp/android-x/message", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["serverInfo"]["name"], "layoutsee")

    def test_direct_tools_list_has_builtin_tools(self) -> None:
        status, payload = self._post("/mcp/android-x/message", {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        self.assertEqual(status, 200)
        names = [t["name"] for t in payload["result"]["tools"]]
        self.assertGreaterEqual(len(names), 12)
        self.assertIn("capture_layout", names)

    def test_unknown_session_falls_back_to_body(self) -> None:
        status, payload = self._post("/mcp/android-x/message?sessionId=ghost", {"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}})
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["serverInfo"]["name"], "layoutsee")

    def test_session_delivers_response_to_outbox(self) -> None:
        session = self.server.mcp_hub.open("android-x")
        status, payload = self._post(
            f"/mcp/android-x/message?sessionId={session.session_id}",
            {"jsonrpc": "2.0", "id": 4, "method": "initialize", "params": {}},
        )
        self.assertEqual(status, 202)
        message = session.outbox.get(timeout=2)
        parsed = json.loads(message)
        self.assertEqual(parsed["id"], 4)
        self.assertEqual(parsed["result"]["serverInfo"]["name"], "layoutsee")


if __name__ == "__main__":
    unittest.main()
