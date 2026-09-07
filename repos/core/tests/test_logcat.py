"""Logcat 读取层单测：重叠对齐、续行归属、游标增量与清空重置。"""

from __future__ import annotations

import json
import secrets
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from layoutsee_core.bootstrap import build_core
from layoutsee_core.logcat import LogcatHub, align, parse_line

DEVICE_ID = "android-stub-1"


def line(index: int, level: str = "I", tag: str = "Demo", message: str = "hello") -> str:
    return f"09-03 10:12:{index:02d}.100  1234  1256 {level} {tag}: {message}"


class StubAdb:
    def __init__(self, dumps: list[list[str]]) -> None:
        self.dumps = dumps
        self.calls = 0
        self.cleared = 0

    def logcat_dump(self, serial: str, lines: int) -> str:
        index = min(self.calls, len(self.dumps) - 1)
        self.calls += 1
        return "\n".join(self.dumps[index]) + "\n"

    def logcat_clear(self, serial: str) -> None:
        self.cleared += 1


class ParseTest(unittest.TestCase):
    def test_parses_threadtime_fields(self) -> None:
        entry = parse_line(line(1, "W", "ActivityManager", "boom: now"), None)
        self.assertEqual(entry["level"], "W")
        self.assertEqual(entry["tag"], "ActivityManager")
        self.assertEqual(entry["pid"], 1234)
        self.assertEqual(entry["tid"], 1256)
        self.assertEqual(entry["message"], "boom: now")
        self.assertFalse(entry["continuation"])

    def test_stack_trace_line_inherits_previous(self) -> None:
        previous = parse_line(line(1, "E", "AndroidRuntime"), None)
        entry = parse_line("\tat com.demo.Main.run(Main.java:12)", previous)
        self.assertTrue(entry["continuation"])
        self.assertEqual(entry["tag"], "AndroidRuntime")
        self.assertEqual(entry["level"], "E")

    def test_separator_line_is_dropped(self) -> None:
        self.assertIsNone(parse_line("--------- beginning of main", None))

    def test_align_returns_only_lines_after_anchor(self) -> None:
        fresh, dropped = align([line(2), line(3)], [line(1), line(2), line(3), line(4)])
        self.assertEqual(fresh, [line(4)])
        self.assertFalse(dropped)

    def test_align_reports_drop_when_anchor_rolled_out(self) -> None:
        fresh, dropped = align([line(1)], [line(8), line(9)])
        self.assertEqual(fresh, [line(8), line(9)])
        self.assertTrue(dropped)


class LogcatHubTest(unittest.TestCase):
    def test_second_poll_only_returns_new_lines(self) -> None:
        adb = StubAdb([[line(1), line(2)], [line(1), line(2), line(3)]])
        hub = LogcatHub(adb)
        first = hub.read("android-x", "x")
        self.assertEqual([item["seq"] for item in first["lines"]], [1, 2])
        second = hub.read("android-x", "x", after=first["cursor"])
        self.assertEqual([item["message"] for item in second["lines"]], ["hello"])
        self.assertEqual([item["seq"] for item in second["lines"]], [3])
        self.assertFalse(second["dropped"])

    def test_idle_poll_returns_nothing(self) -> None:
        adb = StubAdb([[line(1), line(2)]])
        hub = LogcatHub(adb)
        first = hub.read("android-x", "x")
        second = hub.read("android-x", "x", after=first["cursor"])
        self.assertEqual(second["lines"], [])
        self.assertEqual(second["cursor"], first["cursor"])

    def test_dropped_marked_when_device_buffer_rolled(self) -> None:
        adb = StubAdb([[line(1), line(2)], [line(30), line(31)]])
        hub = LogcatHub(adb)
        first = hub.read("android-x", "x")
        second = hub.read("android-x", "x", after=first["cursor"])
        self.assertTrue(second["dropped"])
        self.assertEqual(len(second["lines"]), 2)

    def test_limit_caps_payload_and_keeps_order(self) -> None:
        adb = StubAdb([[line(index) for index in range(1, 40)]])
        hub = LogcatHub(adb)
        payload = hub.read("android-x", "x", limit=5)
        self.assertEqual(len(payload["lines"]), 5)
        self.assertEqual([item["seq"] for item in payload["lines"]], [35, 36, 37, 38, 39])

    def test_clear_resets_cursor_and_buffer(self) -> None:
        adb = StubAdb([[line(1), line(2)], [line(1), line(2)]])
        hub = LogcatHub(adb)
        first = hub.read("android-x", "x")
        self.assertEqual(first["cursor"], 2)
        hub.clear("android-x", "x")
        self.assertEqual(adb.cleared, 1)
        after_clear = hub.read("android-x", "x")
        self.assertEqual(after_clear["cursor"], 2)
        self.assertEqual(after_clear["buffered"], 2)

    def test_stale_cursor_asks_client_to_reset(self) -> None:
        adb = StubAdb([[line(1), line(2)]])
        hub = LogcatHub(adb)
        payload = hub.read("android-x", "x", after=999)
        self.assertTrue(payload["reset"])
        self.assertEqual(len(payload["lines"]), 2)


class LogcatHttpTest(unittest.TestCase):
    """端点行为：读日志不需要会话，清空日志需要会话且受只读门禁与审计约束。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-logcat-http-")
        root = Path(self.temp.name)
        self.context, self.server = build_core(secrets.token_hex(32), data_dir=root / "data", port_start=33620)
        self.adb = StubAdb([[line(1), line(2)]])
        self.adb.devices = lambda: [{
            "deviceId": DEVICE_ID, "platform": "android", "serial": "stub-1", "model": "Stub",
            "product": "stub", "status": "connected", "capabilities": [], "readonly": False, "lastSeenAt": 0,
        }]
        self.adb.available = lambda: True
        self.context.adb = self.adb
        self.context.registry.adb = self.adb
        self.context.logcat = LogcatHub(self.adb)
        self.context.registry.refresh()
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.port = self.server.server_port

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def _call(self, method: str, path: str, *, body: dict | None = None, with_session: bool = True) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"}
        if with_session:
            headers["X-LayoutSee-Session"] = self.context.session_token
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    def test_read_returns_structured_lines_without_session(self) -> None:
        status, payload = self._call("GET", f"/api/v1/devices/{DEVICE_ID}/logcat?limit=10", with_session=False)
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["cursor"], 2)
        self.assertEqual(payload["data"]["lines"][0]["tag"], "Demo")

    def test_invalid_cursor_is_rejected(self) -> None:
        status, payload = self._call("GET", f"/api/v1/devices/{DEVICE_ID}/logcat?after=abc")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_clear_requires_session(self) -> None:
        status, _ = self._call("POST", f"/api/v1/devices/{DEVICE_ID}/logcat/clear", body={}, with_session=False)
        self.assertEqual(status, 403)
        self.assertEqual(self.adb.cleared, 0)

    def test_clear_is_blocked_in_readonly_mode(self) -> None:
        self.context.registry.set_readonly(DEVICE_ID, True)
        status, payload = self._call("POST", f"/api/v1/devices/{DEVICE_ID}/logcat/clear", body={"source": "plugin", "pluginId": "android-logcat"})
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "READ_ONLY_MODE")
        self.assertEqual(self.adb.cleared, 0)

    def test_clear_records_plugin_id_in_audit(self) -> None:
        status, payload = self._call("POST", f"/api/v1/devices/{DEVICE_ID}/logcat/clear", body={"source": "plugin", "pluginId": "android-logcat"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["data"]["cleared"])
        self.assertEqual(self.adb.cleared, 1)
        events = [json.loads(row) for path in sorted(self.context.audit.audit_dir.glob("action-*.jsonl")) for row in path.read_text(encoding="utf-8").splitlines() if row.strip()]
        requested = next(item for item in events if item["kind"] == "requested" and item["actionType"] == "logcat_clear")
        self.assertEqual(requested["source"], "plugin")
        self.assertEqual(requested["pluginId"], "android-logcat")


if __name__ == "__main__":
    unittest.main()
