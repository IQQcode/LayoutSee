from __future__ import annotations

import json
import secrets
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from layoutsee_core.adb import AdbResult
from layoutsee_core.bootstrap import build_core

DEVICE_ID = "android-stub-1"


class StubAdb:
    """只实现终端链路用到的方法；记录最后一次 run 的参数用于断言。"""

    def __init__(self) -> None:
        self.last_args: list[str] | None = None
        self.last_timeout: float | None = None
        self.result = AdbResult(stdout=b"ok\n", stderr=b"", returncode=0)

    def available(self) -> bool:
        return True

    def devices(self) -> list[dict[str, object]]:
        return [{
            "deviceId": DEVICE_ID,
            "platform": "android",
            "serial": "stub-1",
            "model": "Stub",
            "product": "stub",
            "status": "connected",
            "capabilities": ["screenshot"],
            "readonly": False,
            "lastSeenAt": 0,
        }]

    def run(self, args, *, serial=None, timeout=None, check=True) -> AdbResult:
        self.last_args = list(args)
        self.last_timeout = timeout
        return self.result


class DeviceShellTest(unittest.TestCase):
    """终端端点：会话必需、只读拦截、超时收敛、输出截断。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-shell-")
        root = Path(self.temp.name)
        self.nonce = secrets.token_hex(32)
        self.context, self.server = build_core(self.nonce, static_dir=None, data_dir=root / "data", port_start=33580)
        self.adb = StubAdb()
        self.context.adb = self.adb
        self.context.registry.adb = self.adb
        self.context.registry.refresh()
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.port = self.server.server_port

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def _shell(self, body: dict[str, object], *, with_session: bool = True) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json", "Host": f"127.0.0.1:{self.port}"}
        if with_session:
            headers["X-LayoutSee-Session"] = self.context.session_token
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("POST", f"/api/v1/devices/{DEVICE_ID}/shell", body=json.dumps(body), headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    def test_command_is_passed_as_single_argv_entry(self) -> None:
        status, payload = self._shell({"command": "ls -al /sdcard | head -3"})
        self.assertEqual(status, 200)
        self.assertEqual(self.adb.last_args, ["shell", "ls -al /sdcard | head -3"])
        self.assertEqual(payload["data"]["stdout"], "ok\n")
        self.assertEqual(payload["data"]["exitCode"], 0)
        self.assertFalse(payload["data"]["truncated"])

    def test_session_is_required(self) -> None:
        status, payload = self._shell({"command": "id"}, with_session=False)
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "PERMISSION_REQUIRED")
        self.assertIsNone(self.adb.last_args)

    def test_readonly_blocks_shell(self) -> None:
        self.context.registry.set_readonly(DEVICE_ID, True)
        status, payload = self._shell({"command": "rm -rf /sdcard/x"})
        self.assertEqual(payload["error"]["code"], "READ_ONLY_MODE")
        self.assertEqual(status, 403)
        self.assertIsNone(self.adb.last_args)

    def test_empty_command_rejected(self) -> None:
        status, payload = self._shell({"command": "   "})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_overlong_command_rejected(self) -> None:
        status, payload = self._shell({"command": "a" * 2001})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_timeout_is_clamped_to_60s(self) -> None:
        status, payload = self._shell({"command": "id", "timeoutMs": 900_000})
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["timeoutMs"], 60_000)
        self.assertEqual(self.adb.last_timeout, 60.0)

    def test_output_is_truncated_at_256kb(self) -> None:
        self.adb.result = AdbResult(stdout=b"x" * (256 * 1024 + 10), stderr=b"", returncode=1)
        status, payload = self._shell({"command": "cat /dev/urandom"})
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["data"]["stdout"]), 256 * 1024)
        self.assertTrue(payload["data"]["truncated"])
        self.assertEqual(payload["data"]["exitCode"], 1)

    def test_audit_records_command_hash_not_plaintext(self) -> None:
        self._shell({"command": "getprop ro.serialno"})
        lines = [line for path in sorted((self.context.data_dir / "audit").glob("action-*.jsonl")) for line in path.read_text(encoding="utf-8").splitlines()]
        requested = [json.loads(line) for line in lines if json.loads(line)["kind"] == "requested"]
        self.assertTrue(requested)
        event = requested[-1]
        self.assertEqual(event["actionType"], "device_shell")
        self.assertEqual(set(event["params"]), {"chars", "sha256"})
        self.assertNotIn("getprop", json.dumps(event, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
