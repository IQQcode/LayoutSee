from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from layoutsee_core.adb import AdbClient
from layoutsee_core.audit import ActionLog
from layoutsee_core.devices import DeviceGate, DeviceRegistry
from layoutsee_core.settings import SettingsStore
from layoutsee_core.snapshots import SnapshotStore


class StubAdb:
    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    def devices(self) -> list[dict[str, object]]:
        self.calls += 1
        return [{
            "deviceId": "android-stub-1",
            "platform": "android",
            "serial": "stub-1",
            "model": "Stub",
            "product": "stub",
            "status": "connected",
            "capabilities": ["screenshot"],
            "readonly": False,
            "lastSeenAt": 0,
        }]


def run_with_timeout(seconds, fn):
    result: list[object] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            result.append(fn())
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    return thread, result, errors


class LockingRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-lock-")
        self.settings = SettingsStore(Path(self.temp.name))
        self.audit = ActionLog(Path(self.temp.name) / "audit")
        self.gate = DeviceGate()
        self.adb = StubAdb()
        self.registry = DeviceRegistry(self.adb, self.settings, self.audit, self.gate)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_registry_refresh_and_snapshot_do_not_deadlock(self) -> None:
        thread, result, errors = run_with_timeout(3, lambda: (self.registry.refresh(), self.registry.snapshot()))
        self.assertFalse(thread.is_alive(), "refresh/snapshot 死锁：3 秒内未返回")
        self.assertEqual(errors, [])
        items, snapshot = result[0]
        self.assertEqual(len(items), 1)
        self.assertEqual(len(snapshot["items"]), 1)

    def test_settings_update_does_not_deadlock(self) -> None:
        self.settings.get()
        thread, _result, errors = run_with_timeout(3, lambda: self.settings.update({"theme": "dark"}))
        self.assertFalse(thread.is_alive(), "settings.update 死锁：3 秒内未返回")
        self.assertEqual(errors, [])
        self.assertEqual(self.settings.get()["theme"], "dark")

    def test_ref_resolution_does_not_deadlock(self) -> None:
        store = SnapshotStore(secret=b"x" * 32)
        record = {
            "snapshot": {"snapshotId": "snap-x", "deviceId": "android-stub-1", "createdAt": 1},
            "refs": {"0": "rtoken1234_0"},
            "ref_token": "token1234",
            "png": None,
            "xml": "",
            "elements": [],
            "element_to_key": {},
        }
        store.put(record)
        from layoutsee_core.errors import CoreError

        thread, result, errors = run_with_timeout(3, lambda: store.resolve_ref("android-stub-1", "rtoken1234_0"))
        self.assertFalse(thread.is_alive(), "resolve_ref 死锁：3 秒内未返回")
        self.assertEqual(errors, [])
        self.assertEqual(result[0][1], "0")
        with self.assertRaises(CoreError) as context:
            store.resolve_ref("android-stub-1", "rtokenbad_9")
        self.assertEqual(context.exception.code, "REF_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
