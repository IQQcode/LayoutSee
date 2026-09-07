from __future__ import annotations

import json
import secrets
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from layoutsee_core.bootstrap import build_core

INDEX_TEMPLATE = (
    "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
    "<meta name='layoutsee-session' content='__LAYOUTSEE_SESSION__'>"
    "</head><body><div id='root'></div></body></html>"
)


class BrowserHostTest(unittest.TestCase):
    """浏览器宿主：首页注入会话令牌 + Host/Origin 双校验。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-browser-")
        root = Path(self.temp.name)
        self.static_dir = root / "static"
        self.static_dir.mkdir()
        (self.static_dir / "index.html").write_text(INDEX_TEMPLATE, encoding="utf-8")
        self.nonce = secrets.token_hex(32)
        self.context, self.server = build_core(
            self.nonce,
            static_dir=self.static_dir,
            data_dir=root / "data",
            port_start=33540,
        )
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.port = self.server.server_port

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def _request(self, path: str, *, headers: dict[str, str] | None = None) -> tuple[int, str]:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            connection.close()

    def test_index_injects_session_token(self) -> None:
        status, body = self._request("/")
        self.assertEqual(status, 200)
        self.assertIn(self.context.session_token, body)
        self.assertNotIn("__LAYOUTSEE_SESSION__", body)

    def test_index_content_length_matches_injected_body(self) -> None:
        """占位符替换后长度变化，Content-Length 必须按替换后的内容算，否则浏览器会截断首页。"""
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            declared = int(response.getheader("Content-Length"))
            body = response.read()
            self.assertEqual(declared, len(body))
        finally:
            connection.close()

    def test_static_asset_not_rewritten(self) -> None:
        (self.static_dir / "app.js").write_text("const placeholder = '__LAYOUTSEE_SESSION__';", encoding="utf-8")
        status, body = self._request("/app.js")
        self.assertEqual(status, 200)
        self.assertIn("__LAYOUTSEE_SESSION__", body)
        self.assertNotIn(self.context.session_token, body)

    def test_foreign_host_header_rejected(self) -> None:
        status, body = self._request("/api/v1/info", headers={"Host": "layoutsee.example.com"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "PERMISSION_REQUIRED")

    def test_cross_origin_rejected(self) -> None:
        status, body = self._request(
            "/api/v1/info",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": "http://evil.local:8080"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "PERMISSION_REQUIRED")

    def test_same_origin_allowed(self) -> None:
        for host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            with self.subTest(host=host):
                status, body = self._request("/api/v1/info", headers={"Host": host, "Origin": f"http://{host}"})
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(body)["ok"])

    def test_missing_origin_allowed(self) -> None:
        """同源导航、MCP 客户端与命令行工具都不带 Origin，不能因此被拒。"""
        status, body = self._request("/api/v1/info", headers={"Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_health_endpoint_also_guarded(self) -> None:
        status, _ = self._request("/health/ready", headers={"Host": "layoutsee.example.com"})
        self.assertEqual(status, 403)

    def test_paths_endpoint_exposes_directories(self) -> None:
        """浏览器打不开目录，改为展示路径文本，因此 Core 必须把三个目录暴露出来。"""
        status, body = self._request("/api/v1/paths", headers={"Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)
        data = json.loads(body)["data"]
        self.assertEqual(set(data), {"dataDir", "logsDir", "pluginsDir"})
        self.assertTrue(data["logsDir"].endswith("/logs"))
        self.assertTrue(data["logsDir"].startswith(data["dataDir"]))


if __name__ == "__main__":
    unittest.main()
