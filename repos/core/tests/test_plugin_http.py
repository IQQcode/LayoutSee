from __future__ import annotations

import json
import secrets
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

from layoutsee_core.bootstrap import build_core

from test_plugins import write_plugin


def fetch(port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, {key.lower(): value for key, value in response.getheaders()}, response.read()
    finally:
        connection.close()


class PluginHttpTest(unittest.TestCase):
    """插件索引接口与资源托管：策略头、路径逃逸与索引派生视图。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-plugin-http-")
        root = Path(self.temp.name)
        self.builtin = root / "builtin"
        self.builtin.mkdir()
        write_plugin(root / "plugins", "demo", permissions=["snapshot.read"])
        # 避免读到随包内置插件，测试只看临时目录
        self._env_patch = mock.patch.dict("os.environ", {"LAYOUTSEE_BUILTIN_PLUGINS": str(self.builtin)})
        self._env_patch.start()
        self.context, self.server = build_core(secrets.token_hex(32), data_dir=root, port_start=33560)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.port = self.server.server_port

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._env_patch.stop()
        self.temp.cleanup()

    def test_index_endpoint_reports_ready_plugin(self) -> None:
        status, _, body = fetch(self.port, "/api/v1/plugins/index")
        self.assertEqual(status, 200)
        payload = json.loads(body)["data"]
        self.assertEqual(payload["schemaVersion"], "1.0")
        self.assertEqual([item["id"] for item in payload["items"]], ["demo"])
        self.assertEqual(payload["items"][0]["status"], "ready")
        self.assertEqual(payload["items"][0]["origin"], "local")
        self.assertTrue(json.loads(fetch(self.port, "/api/v1/plugins/index")[2])["data"]["cacheHit"])
        self.assertFalse(json.loads(fetch(self.port, "/api/v1/plugins/index?refresh=true")[2])["data"]["cacheHit"])

    def test_legacy_list_endpoint_derives_from_index(self) -> None:
        status, _, body = fetch(self.port, "/api/v1/plugins")
        self.assertEqual(status, 200)
        items = json.loads(body)["data"]["items"]
        self.assertEqual(items[0]["id"], "demo")
        self.assertEqual(items[0]["status"], "loaded")
        self.assertEqual(items[0]["entry"], "index.html")

    def test_asset_served_with_plugin_scoped_csp(self) -> None:
        status, headers, body = fetch(self.port, "/plugin-assets/demo/index.html")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"<!doctype html>"))
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")
        csp = headers["content-security-policy"]
        self.assertIn("connect-src 'none'", csp)
        self.assertIn(f"frame-ancestors http://127.0.0.1:{self.port}", csp)
        self.assertNotIn("'self'", csp)  # sandbox iframe 是 opaque origin，'self' 匹配不到任何来源

    def test_main_document_allows_same_origin_frames(self) -> None:
        _, headers, _ = fetch(self.port, "/api/v1/info")
        self.assertIn("frame-src 'self'", headers["content-security-policy"])

    def test_asset_escape_and_unknown_plugin_rejected(self) -> None:
        status, _, body = fetch(self.port, "/plugin-assets/demo/../../etc/hosts")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "PERMISSION_REQUIRED")
        status, _, body = fetch(self.port, "/plugin-assets/ghost/index.html")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"]["code"], "PLUGIN_NOT_FOUND")

    def test_asset_policy_does_not_leak_to_next_request(self) -> None:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", "/plugin-assets/demo/index.html")
            connection.getresponse().read()
            connection.request("GET", "/api/v1/info")
            response = connection.getresponse()
            policy = response.getheader("Content-Security-Policy")
            response.read()
        finally:
            connection.close()
        self.assertIn("default-src 'self'", policy)


class BuiltinPluginTest(unittest.TestCase):
    """内置插件随包：不覆盖 LAYOUTSEE_BUILTIN_PLUGINS，跑真实目录的端到端链路。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-builtin-")
        self.context, self.server = build_core(secrets.token_hex(32), data_dir=Path(self.temp.name), port_start=33600)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.port = self.server.server_port

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def test_builtin_plugin_is_indexed_and_served(self) -> None:
        payload = json.loads(fetch(self.port, "/api/v1/plugins/index")[2])["data"]
        entry = next(item for item in payload["items"] if item["id"] == "snapshot-overview")
        self.assertEqual(entry["status"], "ready")
        self.assertEqual(entry["origin"], "builtin")
        self.assertEqual(entry["contributions"]["workbenchTabs"][0]["entry"], "index.html")
        for asset, content_type in (("index.html", "text/html"), ("app.js", "text/javascript"), ("style.css", "text/css")):
            status, headers, _ = fetch(self.port, f"/plugin-assets/snapshot-overview/{asset}")
            self.assertEqual(status, 200, asset)
            self.assertIn(content_type, headers["content-type"])

    def test_builtin_declarative_tool_joins_catalog(self) -> None:
        tools = json.loads(fetch(self.port, "/api/v1/mcp/tools")[2])["data"]
        self.assertEqual(tools["builtinCount"], 12)
        names = [item["name"] for item in tools["tools"]]
        self.assertEqual(len(names[:12]), 12)
        self.assertIn("plugin.snapshot-overview.capture_then_summarize", names)

    def test_logcat_plugin_is_app_only_and_served(self) -> None:
        payload = json.loads(fetch(self.port, "/api/v1/plugins/index")[2])["data"]
        entry = next(item for item in payload["items"] if item["id"] == "android-logcat")
        self.assertEqual(entry["status"], "ready")
        # 只声明 app 宿主：浏览器宿主下 buildExtensionModel 会把它过滤进 unavailable
        self.assertEqual(entry["hosts"], ["app"])
        self.assertEqual(entry["devicePlatforms"], ["android"])
        self.assertEqual(entry["contributions"]["workbenchTabs"][0]["id"], "logcat")
        self.assertIn("device.write", entry["permissions"])
        for asset in ("index.html", "app.js", "style.css"):
            status, _, _ = fetch(self.port, f"/plugin-assets/android-logcat/{asset}")
            self.assertEqual(status, 200, asset)


if __name__ == "__main__":
    unittest.main()
