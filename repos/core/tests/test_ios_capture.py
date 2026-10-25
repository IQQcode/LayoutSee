from __future__ import annotations

import json
import secrets
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from layoutsee_core.bootstrap import build_core
from layoutsee_core.errors import CoreError

ANDROID_DEVICE_ID = "android-stub-1"
IOS_DEVICE_ID = "ios-udid-1"

IOS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<hierarchy rotation="0">'
    '<node index="0" class="UIView" bounds="[0,0][1170,2532]" text="" resource-id="" content-desc="" '
    'enabled="true" clickable="false" scrollable="false">'
    '<node index="0" class="UIButton" bounds="[60,120][540,220]" text="登录" resource-id="login-button" '
    'content-desc="" enabled="true" clickable="true" scrollable="false"/>'
    '</node>'
    '</hierarchy>'
)

ANDROID_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<hierarchy rotation="0">'
    '<node index="0" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" text="" resource-id="" '
    'content-desc="" enabled="true" clickable="false" scrollable="false"/>'
    '</hierarchy>'
)


def tiny_png(width: int, height: int) -> bytes:
    """仅含宽高的伪 PNG：png_size 只读魔数与 16-24 字节的尺寸段。"""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x00" * 8


class StubIOSDriver:
    """duck-typing IOSDeviceDriver：不触 socket，返回固定枚举与抓取结果。"""

    def __init__(self) -> None:
        self.capture_error: CoreError | None = None
        self.capture_udids: list[str] = []

    def available(self) -> bool:
        return True

    def devices(self) -> list[dict[str, object]]:
        return [{
            "deviceId": IOS_DEVICE_ID,
            "platform": "ios",
            "serial": "udid-1",
            "model": "",
            "product": "iPhone14,2",
            "status": "connected",
            "capabilities": ["layout"],
            "readonly": True,
            "lastSeenAt": 0,
        }]

    def capture(self, udid: str) -> dict[str, object]:
        self.capture_udids.append(udid)
        if self.capture_error is not None:
            raise self.capture_error
        return {
            "xml": IOS_XML,
            "window_size": {"width": 1170, "height": 2532},
            "app": {"appName": "LookinDemo", "appBundleIdentifier": "com.qmui.lookindemo"},
            "warnings": [],
        }


class StubAdb:
    """Android 侧回归桩：覆盖抓取链用到的方法。"""

    def available(self) -> bool:
        return True

    def devices(self) -> list[dict[str, object]]:
        return [{
            "deviceId": ANDROID_DEVICE_ID,
            "platform": "android",
            "serial": "stub-1",
            "model": "Stub",
            "product": "stub",
            "status": "connected",
            "capabilities": ["screenshot", "layout", "input", "apps", "media-screenshot-fallback"],
            "readonly": False,
            "lastSeenAt": 0,
        }]

    def current_app(self, serial: str) -> dict[str, str]:
        return {"packageName": "com.example", "activity": "MainActivity"}

    def window_size(self, serial: str) -> dict[str, int]:
        return {"width": 1080, "height": 2400}

    def orientation(self, serial: str) -> str:
        return "portrait"

    def density(self, serial: str) -> int | None:
        return 420

    def dump_xml(self, serial: str) -> str:
        return ANDROID_XML

    def screenshot(self, serial: str) -> bytes:
        return tiny_png(1080, 2400)


class IOSCaptureTest(unittest.TestCase):
    """iOS 设备源接入：注册表双源合并、分平台抓取、只读门禁与 Android 回归。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-ios-")
        root = Path(self.temp.name)
        self.nonce = secrets.token_hex(32)
        self.context, self.server = build_core(self.nonce, static_dir=None, data_dir=root / "data", port_start=33640)
        self.ios = StubIOSDriver()
        self.adb = StubAdb()
        # 热替换：先换 stub 再 refresh，真实驱动不会触 socket
        self.context.ios = self.ios
        self.context.registry.ios = self.ios
        self.context.capture.ios = self.ios
        self.context.adb = self.adb
        self.context.registry.adb = self.adb
        self.context.capture.adb = self.adb  # 抓取协调器持有独立的 adb 引用，需一并替换
        self.context.registry.refresh()
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.port = self.server.server_port

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def _request(self, method: str, path: str, body: dict[str, object] | None = None, *, with_session: bool = True) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"}
        if with_session:
            headers["X-LayoutSee-Session"] = self.context.session_token
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
        finally:
            connection.close()

    def _get(self, path: str) -> tuple[int, dict]:
        return self._request("GET", path)

    def _post(self, path: str, body: dict[str, object] | None = None) -> tuple[int, dict]:
        return self._request("POST", path, body or {})

    def _capture_ios(self) -> str:
        status, payload = self._post(f"/api/v1/devices/{IOS_DEVICE_ID}/snapshots")
        self.assertEqual(status, 200)
        return str(payload["data"]["snapshotId"])

    def test_devices_list_contains_ios_entry(self) -> None:
        status, payload = self._get("/api/v1/devices")
        self.assertEqual(status, 200)
        items = {item["deviceId"]: item for item in payload["data"]["items"]}
        ios = items[IOS_DEVICE_ID]
        self.assertEqual(ios["platform"], "ios")
        self.assertEqual(ios["capabilities"], ["layout"])
        self.assertTrue(ios["readonly"])
        self.assertEqual(ios["status"], "connected")
        # 回归：Android 设备同表共存
        self.assertIn(ANDROID_DEVICE_ID, items)
        self.assertEqual(items[ANDROID_DEVICE_ID]["platform"], "android")

    def test_ios_capture_returns_android_isomorphic_record(self) -> None:
        status, payload = self._post(f"/api/v1/devices/{IOS_DEVICE_ID}/snapshots")
        self.assertEqual(status, 200)
        self.assertEqual(self.ios.capture_udids, ["udid-1"])  # capture 收到 udid
        data = payload["data"]
        self.assertEqual(data["windowSizePx"], {"width": 1170, "height": 2532})
        self.assertEqual(data["synchronization"], "best_effort")
        self.assertEqual(data["hierarchyAccuracy"], "best_effort")
        self.assertTrue(data["warnings"])

        snapshot_id = data["snapshotId"]
        status, detail = self._get(f"/api/v1/snapshots/{snapshot_id}")
        self.assertEqual(status, 200)
        snapshot = detail["data"]
        self.assertEqual(snapshot["deviceId"], IOS_DEVICE_ID)
        self.assertEqual(snapshot["windowSizePx"], {"width": 1170, "height": 2532})
        self.assertIsNone(snapshot["screenshot"])
        self.assertEqual(snapshot["density"], None)
        self.assertEqual(snapshot["foreground"]["appName"], "LookinDemo")
        self.assertEqual(snapshot["foreground"]["appBundleIdentifier"], "com.qmui.lookindemo")
        self.assertTrue(snapshot["warnings"])
        nodes = snapshot["nodes"]
        self.assertEqual(nodes[0]["boundsPx"], {"left": 0, "top": 0, "right": 1170, "bottom": 2532})
        button = next(node for node in nodes if node["className"] == "UIButton")
        self.assertEqual(button["boundsPx"], {"left": 60, "top": 120, "right": 540, "bottom": 220})
        self.assertEqual(button["text"], "登录")
        self.assertEqual(button["resourceId"], "login-button")
        self.assertTrue(button["clickable"])
        self.assertEqual(snapshot["roots"], [nodes[0]["nodeKey"]])

    def test_ios_window_size_without_snapshot_returns_404(self) -> None:
        status, payload = self._get(f"/api/v1/devices/{IOS_DEVICE_ID}/window-size")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "SNAPSHOT_STALE")

    def test_ios_window_size_from_latest_snapshot(self) -> None:
        self._capture_ios()
        status, payload = self._get(f"/api/v1/devices/{IOS_DEVICE_ID}/window-size")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"], {"width": 1170, "height": 2532})

    def test_ios_media_capabilities_report_none(self) -> None:
        status, payload = self._get(f"/api/v1/devices/{IOS_DEVICE_ID}/media/capabilities")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["mode"], "none")
        self.assertFalse(payload["data"]["live"])

    def test_ios_current_app_reads_latest_snapshot(self) -> None:
        status, payload = self._get(f"/api/v1/devices/{IOS_DEVICE_ID}/current-app")
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "LOOKIN_APP_NOT_FOUND")
        self._capture_ios()
        status, payload = self._get(f"/api/v1/devices/{IOS_DEVICE_ID}/current-app")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["appName"], "LookinDemo")

    def test_ios_apps_returns_empty_with_note(self) -> None:
        status, payload = self._get(f"/api/v1/devices/{IOS_DEVICE_ID}/apps")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["items"], [])
        self.assertTrue(payload["data"]["note"])

    def test_ios_actions_and_shell_blocked_with_read_only(self) -> None:
        for path, body in (
            (f"/api/v1/devices/{IOS_DEVICE_ID}/actions", {"type": "tap", "payload": {"x": 1, "y": 2}}),
            (f"/api/v1/devices/{IOS_DEVICE_ID}/shell", {"command": "id"}),
        ):
            status, payload = self._post(path, body)
            self.assertEqual(status, 403)
            self.assertEqual(payload["error"]["code"], "READ_ONLY_MODE")

    def test_ios_screenshot_and_logcat_blocked_with_read_only(self) -> None:
        for path in (f"/api/v1/devices/{IOS_DEVICE_ID}/screenshot", f"/api/v1/devices/{IOS_DEVICE_ID}/logcat"):
            status, payload = self._get(path)
            self.assertEqual(status, 403)
            self.assertEqual(payload["error"]["code"], "READ_ONLY_MODE")

    def test_ios_logcat_clear_blocked_with_read_only(self) -> None:
        status, payload = self._post(f"/api/v1/devices/{IOS_DEVICE_ID}/logcat/clear")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "READ_ONLY_MODE")

    def test_ios_capture_maps_lookin_error_to_http_status(self) -> None:
        self.ios.capture_error = CoreError("LOOKIN_APP_NOT_FOUND", "未找到前台运行的 Lookin App。")
        status, payload = self._post(f"/api/v1/devices/{IOS_DEVICE_ID}/snapshots")
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "LOOKIN_APP_NOT_FOUND")

    def test_android_capture_regression(self) -> None:
        status, payload = self._post(f"/api/v1/devices/{ANDROID_DEVICE_ID}/snapshots")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["windowSizePx"], {"width": 1080, "height": 2400})
        snapshot_id = payload["data"]["snapshotId"]
        status, detail = self._get(f"/api/v1/snapshots/{snapshot_id}")
        self.assertEqual(status, 200)
        snapshot = detail["data"]
        self.assertIsNotNone(snapshot["screenshot"])
        self.assertEqual(snapshot["screenshot"]["width"], 1080)
        self.assertEqual(snapshot["screenshot"]["height"], 2400)
        nodes = snapshot["nodes"]
        self.assertEqual(nodes[0]["className"], "android.widget.FrameLayout")
        self.assertEqual(nodes[0]["boundsPx"], {"left": 0, "top": 0, "right": 1080, "bottom": 2400})

    def test_android_media_capabilities_unchanged(self) -> None:
        status, payload = self._get(f"/api/v1/devices/{ANDROID_DEVICE_ID}/media/capabilities")
        self.assertEqual(status, 200)
        self.assertIn(payload["data"]["mode"], ("scrcpy", "screenshot"))


if __name__ == "__main__":
    unittest.main()
