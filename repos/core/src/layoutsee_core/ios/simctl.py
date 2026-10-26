"""SimctlClient：xcrun simctl 的最小封装（模拟器截图画布背景）。

仅封装随 macOS/Xcode 分发的 `xcrun`（子进程范式与 AdbClient 调 adb 一致）；
网络链路仍全部由 ios 包内纯 socket 完成。真机截图（pymobiledevice3）后续补。
所有 subprocess argv 均为全字面量（无外部输入参与），shell 保持关闭。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

XCRUN_PATH = "/usr/bin/xcrun"
# 固定临时截图路径：抓取由 DeviceGate 串行化，跨进程极端并发下允许覆盖重写
SCREENSHOT_TEMP_PATH = "/tmp/layoutsee-sim-screenshot.png"


class SimctlClient:
    """`xcrun simctl` 子进程封装：booted 模拟器截图。"""

    def booted_udids(self) -> list[str]:
        """当前 booted 模拟器 UDID 列表（无 booted 或 xcrun 不可用返回空）。"""
        try:
            result = subprocess.run(
                [XCRUN_PATH, "simctl", "list", "devices", "booted", "-j"],
                capture_output=True,
                timeout=10.0,
                check=True,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        try:
            payload = json.loads(result.stdout.decode("utf-8", "replace"))
        except (ValueError, UnicodeDecodeError):
            return []
        devices = payload.get("devices") if isinstance(payload, dict) else None
        udids: list[str] = []
        if isinstance(devices, dict):
            for entries in devices.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("state") == "Booted" and entry.get("udid"):
                        udids.append(str(entry["udid"]))
        return udids

    def screenshot(self) -> bytes | None:
        """截取 booted 模拟器屏幕 PNG。

        仅当恰好一台 booted 模拟器时执行（多台时无法对应到 serial，由调用方降级为
        线框渲染并提示）；失败返回 None，不抛异常。
        """
        if len(self.booted_udids()) != 1:
            return None
        try:
            subprocess.run(
                [XCRUN_PATH, "simctl", "io", "booted", "screenshot", "--type=png", SCREENSHOT_TEMP_PATH],
                capture_output=True,
                timeout=15.0,
                check=True,
                shell=False,
            )
            png = Path(SCREENSHOT_TEMP_PATH).read_bytes()
            try:
                Path(SCREENSHOT_TEMP_PATH).unlink()
            except OSError:
                pass
            return png
        except (OSError, subprocess.SubprocessError):
            return None
