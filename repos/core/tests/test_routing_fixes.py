from __future__ import annotations

import json
import secrets
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlparse

from layoutsee_core.bootstrap import build_core

# 测试请求仅允许回环地址上的本地 Core（SSRF 边界：协议 + 主机白名单）
ALLOWED_TEST_HOSTS = frozenset({"127.0.0.1"})


def request(url: str, *, method: str = "GET", token: str | None = None, payload: dict | None = None):
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ALLOWED_TEST_HOSTS or parsed.port is None:
        raise ValueError(f"测试仅允许 http 回环地址：{url}")
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    try:
        body = json.dumps(payload) if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-LayoutSee-Session"] = token
        connection.request(method, parsed.path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        status = response.status
    finally:
        connection.close()
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw


class RoutingFixTest(unittest.TestCase):
    """回归：带斜杠子路由（snapshots/latest、media/capabilities）与 OPTIONS 预检。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-routing-")
        self.nonce = secrets.token_hex(32)
        self.context, self.server = build_core(self.nonce, data_dir=Path(self.temp.name), port_start=33520)
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    @property
    def token(self) -> str:
        return self.context.session_token

    def test_snapshot_latest_route(self) -> None:
        status, payload = request(f"{self.base}/api/v1/devices/android-x/snapshots/latest")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["data"]["snapshotId"])

    def test_media_capabilities_route(self) -> None:
        status, payload = request(f"{self.base}/api/v1/devices/android-x/media/capabilities")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("mode", payload["data"])

    def test_options_preflight_returns_204(self) -> None:
        status, _ = request(f"{self.base}/api/v1/devices/android-x/snapshots", method="OPTIONS")
        self.assertEqual(status, 204)

    def test_unknown_route_still_reports(self) -> None:
        status, payload = request(f"{self.base}/api/v1/devices/android-x/unknown-sub")
        self.assertEqual(status, 503)
        self.assertFalse(payload["ok"])

    def test_snapshot_detail_route(self) -> None:
        status, payload = request(f"{self.base}/api/v1/snapshots/snap-missing")
        self.assertEqual(status, 409)  # SNAPSHOT_STALE
        self.assertEqual(payload["error"]["code"], "SNAPSHOT_STALE")

    def test_keepalive_body_leftover_does_not_poison_next_request(self) -> None:
        """回归：POST 带请求体但不读 body 的路由，响应后必须排空 body，
        否则残留字节会让 keep-alive 上的下一个请求解析成 `{}GET` 之类的 501（真机踩坑）。"""
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            # 走一个存在但不读 body 的写路由（settings 需要令牌会 403，但同样不读 body）
            body = json.dumps({"schemaVersion": "1.0", "theme": "dark"}).encode()
            connection.request("PUT", "/api/v1/settings", body=body, headers={"Content-Type": "application/json"})
            first = connection.getresponse()
            first.read()
            self.assertEqual(first.status, 403)
            # 同一连接上的下一个请求必须被正常解析
            connection.request("GET", "/api/v1/info")
            second = connection.getresponse()
            payload = json.loads(second.read())
            self.assertEqual(second.status, 200)
            self.assertTrue(payload["ok"])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
