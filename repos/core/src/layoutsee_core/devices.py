from __future__ import annotations

import hashlib
import threading
import time
from contextlib import contextmanager

from .adb import AdbClient
from .audit import ActionLog
from .errors import CoreError
from .ios import IOSDeviceDriver
from .settings import SettingsStore

SCAN_TIMEOUT_S = 8.0


def device_id_for(serial: str) -> str:
    return f"android-{serial}"


class DeviceGate:
    """每设备串行写队列：抓取持有期间写请求等待，超时返回 DEVICE_BUSY。"""

    def __init__(self, wait_ms: int = 5_000) -> None:
        self._wait = wait_ms / 1000
        self._locks: dict[str, threading.Condition] = {}
        self._busy: dict[str, bool] = {}
        self._meta_lock = threading.Lock()

    def _condition(self, device_id: str) -> threading.Condition:
        with self._meta_lock:
            condition = self._locks.get(device_id)
            if condition is None:
                condition = threading.Condition()
                self._locks[device_id] = condition
                self._busy[device_id] = False
            return condition

    @contextmanager
    def acquire(self, device_id: str):
        condition = self._condition(device_id)
        deadline = time.monotonic() + self._wait
        with condition:
            while self._busy[device_id]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CoreError(
                        "DEVICE_BUSY",
                        "设备正忙，请稍后重试。",
                        retryable=True,
                        details={"deviceId": device_id, "waitMs": self._wait * 1000},
                    )
                condition.wait(remaining)
            self._busy[device_id] = True
        try:
            yield
        finally:
            with condition:
                self._busy[device_id] = False
                condition.notify_all()


class DeviceRegistry:
    """后台轮询 ADB + iOS（usbmux）双源枚举；失败保留上一轮结果；消失设备标记 offline。"""

    def __init__(
        self,
        adb: AdbClient,
        settings: SettingsStore,
        audit: ActionLog,
        gate: DeviceGate,
        ios: IOSDeviceDriver | None = None,
    ) -> None:
        self.adb = adb
        self.ios = ios
        self.settings = settings
        self.audit = audit
        self.gate = gate
        self._lock = threading.Lock()
        self._devices: dict[str, dict[str, object]] = {}
        self._readonly: dict[str, bool] = {}
        self._last_error: str | None = None
        self._refreshed_at_ms: int = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._poll_loop, name="layoutsee-device-registry", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _poll_loop(self) -> None:
        self.refresh()
        while not self._stop.wait(self.poll_interval()):
            self.refresh()

    def poll_interval(self) -> float:
        value = self.settings.get().get("pollIntervalMs", 5000)
        try:
            return max(1.0, min(60.0, float(value) / 1000))
        except (TypeError, ValueError):
            return 5.0

    def refresh(self) -> list[dict[str, object]]:
        """同一轮询线程内先扫 adb 再扫 iOS，合并进设备表；任一数据源失败只保留该平台上一轮结果。"""
        errors: list[str] = []
        android_scanned: list[dict[str, object]] = []
        android_failed = True
        if not self.adb.available():
            errors.append("ADB_NOT_FOUND: 未找到 adb，请在设置中指定路径")
        else:
            try:
                android_scanned = self.adb.devices()
                android_failed = False
            except CoreError as error:
                errors.append(f"{error.code}: {error.message}")
            except Exception:
                errors.append("CORE_UNAVAILABLE: 设备枚举失败，已保留上一轮结果")

        # iOS 扫描结果：None 表示枚举失败（保留上一轮 iOS 设备）；列表（含空）表示本轮扫描结果。
        # ios.available() 为 False 时视为本轮无 iOS 设备（空列表），离线标记照常生效。
        ios_scanned: list[dict[str, object]] | None = []
        if self.ios is not None:
            ios_scanned = None
            if self.ios.available():
                try:
                    ios_scanned = self.ios.devices()
                except CoreError as error:
                    errors.append(f"{error.code}: {error.message}")
                except Exception:
                    errors.append("LOOKIN_UNAVAILABLE: iOS 设备枚举失败，已保留上一轮结果")

        now_ms = int(time.time() * 1000)
        with self._lock:
            seen: set[str] = set()
            if android_failed:
                # adb 本轮失败：Android 设备保留上一轮结果，不参与离线标记（与既有失败语义一致）
                for device_id, descriptor in self._devices.items():
                    if str(descriptor.get("platform")) != "ios":
                        seen.add(device_id)
            else:
                for descriptor in android_scanned:
                    device_id = str(descriptor["deviceId"])
                    seen.add(device_id)
                    previous = self._devices.get(device_id)
                    if previous is not None and previous.get("status") == "offline" and descriptor.get("status") == "connected":
                        descriptor["status"] = "connected"
                    descriptor["readonly"] = self._readonly.get(device_id, bool(self.settings.get().get("defaultReadonly")))
                    descriptor["lastSeenAt"] = now_ms
                    self._devices[device_id] = descriptor
            if ios_scanned is None:
                # iOS 枚举失败：保留上一轮 iOS 设备，不参与离线标记
                for device_id, descriptor in self._devices.items():
                    if str(descriptor.get("platform")) == "ios":
                        seen.add(device_id)
            else:
                for descriptor in ios_scanned:
                    device_id = str(descriptor["deviceId"])
                    seen.add(device_id)
                    # iOS 恒只读：保持 descriptor 自带 readonly=True，不用 defaultReadonly 覆盖
                    descriptor["lastSeenAt"] = now_ms
                    self._devices[device_id] = descriptor
            for device_id, descriptor in list(self._devices.items()):
                if device_id not in seen and descriptor.get("status") not in ("offline",):
                    descriptor = dict(descriptor)
                    descriptor["status"] = "offline"
                    descriptor["capabilities"] = []
                    descriptor["lastSeenAt"] = now_ms
                    self._devices[device_id] = descriptor
            self._last_error = "\n".join(errors) if errors else None
            if not android_failed or (self.ios is not None and ios_scanned is not None):
                self._refreshed_at_ms = now_ms
            items = [dict(value) for value in self._devices.values()]
        items.sort(key=lambda item: str(item.get("deviceId")))
        return items

    def list_devices(self) -> list[dict[str, object]]:
        with self._lock:
            items = [dict(value) for value in self._devices.values()]
        items.sort(key=lambda item: str(item.get("deviceId")))
        return items

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            items = [dict(value) for value in self._devices.values()]
            last_error = self._last_error
            refreshed_at = self._refreshed_at_ms
        items.sort(key=lambda item: str(item.get("deviceId")))
        return {"items": items, "lastError": last_error, "refreshedAt": refreshed_at}

    def device(self, device_id: str) -> dict[str, object]:
        with self._lock:
            descriptor = self._devices.get(device_id)
            if descriptor is None:
                raise CoreError("DEVICE_NOT_FOUND", "设备不存在，可能已经断开。", details={"deviceId": device_id})
            if descriptor.get("status") == "unauthorized":
                raise CoreError("DEVICE_UNAUTHORIZED", "设备未授权，请在设备上确认 USB 调试授权。", details={"deviceId": device_id})
            if descriptor.get("status") in ("offline", "error"):
                raise CoreError("DEVICE_OFFLINE", "设备已离线，已保留最后画面与快照。", details={"deviceId": device_id})
            return dict(descriptor)

    def serial_for(self, device_id: str) -> str:
        """返回设备序列号：Android 为 adb serial，iOS 为 udid（descriptor["serial"]）。"""
        descriptor = self.device(device_id)
        return str(descriptor["serial"])

    def is_readonly(self, device_id: str) -> bool:
        descriptor = self.device(device_id)
        if str(descriptor.get("platform")) == "ios":
            return True  # iOS 恒只读：Lookin 无 tap/输入注入能力
        if bool(descriptor.get("readonly")):
            return True
        with self._lock:
            return bool(self._readonly.get(device_id))

    def set_readonly(self, device_id: str, flag: bool) -> dict[str, object]:
        self.device(device_id)
        with self._lock:
            self._readonly[device_id] = bool(flag)
            if device_id in self._devices:
                self._devices[device_id]["readonly"] = bool(flag)
        self.audit.record({
            "kind": "config",
            "timestampMs": int(time.time() * 1000),
            "deviceIdHash": hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:12],
            "change": {"readonly": bool(flag)},
        })
        return {"deviceId": device_id, "readonly": bool(flag)}
