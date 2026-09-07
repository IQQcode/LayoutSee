from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import CoreError

# Finder 启动的 GUI 应用拿不到终端 PATH，这里兜底探测常见 adb 位置。
ADB_CANDIDATE_PATHS = (
    "/opt/local/bin/adb",                    # MacPorts
    "/opt/homebrew/bin/adb",                 # Homebrew (Apple Silicon)
    "/usr/local/bin/adb",                    # Homebrew (Intel)
    "~/Library/Android/sdk/platform-tools/adb",
    "~/Android/Sdk/platform-tools/adb",
)


def find_adb(configured: str | None = None) -> str | None:
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_file() and os.access(configured_path, os.X_OK):
            return str(configured_path)
    found = shutil.which("adb")
    if found:
        return found
    for candidate in ADB_CANDIDATE_PATHS:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


@dataclass(frozen=True)
class AdbResult:
    stdout: bytes
    stderr: bytes
    returncode: int

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace").strip()


class AdbClient:
    def __init__(self, executable: str | None = None, timeout: float = 8.0, resolver=None) -> None:
        self.configured_executable = executable
        self.timeout = timeout
        self._resolver = resolver

    @property
    def executable(self) -> str | None:
        if self._resolver:
            resolved = self._resolver()
            if resolved:
                return resolved
        return find_adb(self.configured_executable)

    def available(self) -> bool:
        return bool(self.executable)

    def run(self, args: list[str], *, serial: str | None = None, timeout: float | None = None, check: bool = True) -> AdbResult:
        executable = self.executable
        if not executable:
            raise CoreError(
                "ADB_NOT_FOUND",
                "未找到 adb，请在设置中指定路径或安装 Android platform-tools。",
                details={"hint": "安装 platform-tools 后重新检测设备"},
            )
        command = [executable]
        if serial:
            command.extend(["-s", serial])
        command.extend(args)
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout or self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise CoreError(
                "OPERATION_TIMEOUT",
                "ADB 操作超时，请确认设备连接状态后重试。",
                retryable=True,
                details={"command": " ".join(shlex.quote(part) for part in args)},
            ) from error
        result = AdbResult(completed.stdout, completed.stderr, completed.returncode)
        if check and completed.returncode != 0:
            message = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
            code = "DEVICE_DISCONNECTED" if "device" in message.lower() else "CORE_UNAVAILABLE"
            raise CoreError(code, message or "ADB 操作失败。", retryable=True)
        return result

    def devices(self) -> list[dict[str, object]]:
        if not self.available():
            return []
        result = self.run(["devices", "-l"])
        now = int(time.time() * 1000)
        devices: list[dict[str, object]] = []
        for line in result.text.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, raw_state = parts[0], parts[1]
            fields = dict(part.split(":", 1) for part in parts[2:] if ":" in part)
            status = {"device": "connected", "unauthorized": "unauthorized", "offline": "offline"}.get(raw_state, "error")
            devices.append({
                "deviceId": f"android-{serial}",
                "platform": "android",
                "serial": serial,
                "model": fields.get("model", ""),
                "product": fields.get("product", ""),
                "status": status,
                "capabilities": ["screenshot", "layout", "input", "apps", "media-screenshot-fallback"] if status == "connected" else [],
                "readonly": False,
                "lastSeenAt": now,
            })
        return devices

    def diagnostics(self, serial: str | None = None) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        checks.append({
            "name": "adbExecutable",
            "status": "pass" if self.available() else "fail",
            "message": self.executable or "未找到 adb",
            "hint": "在设置中指定 adb 路径或安装 Android platform-tools" if not self.available() else "",
        })
        if serial and self.available():
            state = self.run(["get-state"], serial=serial, check=False)
            connected = state.returncode == 0 and state.text == "device"
            checks.append({
                "name": "deviceAuthorization",
                "status": "pass" if connected else "fail",
                "message": state.text or state.stderr.decode("utf-8", errors="replace").strip() or "设备不可用",
                "hint": "检查数据线，并在设备上确认 USB 调试授权" if not connected else "",
            })
            if connected:
                u2 = self.run(["shell", "pm", "path", "com.github.uiautomator"], serial=serial, check=False)
                checks.append({
                    "name": "uiautomator2",
                    "status": "pass" if u2.returncode == 0 and u2.text else "unknown",
                    "message": "已检测到 uiautomator2" if u2.returncode == 0 and u2.text else "未检测到 uiautomator2，当前将使用系统 uiautomator dump",
                    "hint": "如需增强能力，可安装并初始化 uiautomator2" if not u2.text else "",
                })
        return {"platform": "android", "checks": checks, "healthy": all(item["status"] == "pass" for item in checks if item["status"] != "unknown")}

    def window_size(self, serial: str) -> dict[str, int]:
        text = self.run(["shell", "wm", "size"], serial=serial).text
        matches = re.findall(r"(\d+)x(\d+)", text)
        if not matches:
            raise CoreError("CORE_UNAVAILABLE", "无法读取设备窗口尺寸。", retryable=True)
        width, height = matches[-1]
        return {"width": int(width), "height": int(height)}

    def density(self, serial: str) -> int | None:
        text = self.run(["shell", "wm", "density"], serial=serial, check=False).text
        matches = re.findall(r"[Dd]ensity:\s*(\d+)", text)
        if matches:
            return int(matches[-1])
        matches = re.findall(r"(\d+)\s*dpi", text)
        return int(matches[-1]) if matches else None

    def orientation(self, serial: str) -> str:
        text = self.run(["shell", "dumpsys", "input"], serial=serial, check=False).text
        match = re.search(r"SurfaceOrientation:\s*(\d)", text)
        if match:
            return {"0": "portrait", "1": "landscape", "2": "portrait", "3": "landscape"}.get(match.group(1), "portrait")
        size = self.window_size(serial)
        return "landscape" if size["width"] > size["height"] else "portrait"

    def current_app(self, serial: str) -> dict[str, str]:
        outputs = [
            self.run(["shell", "dumpsys", "window", "windows"], serial=serial, check=False).text,
            self.run(["shell", "dumpsys", "activity", "activities"], serial=serial, check=False).text,
        ]
        pattern = re.compile(r"(?:mCurrentFocus|mResumedActivity).*?\s([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)")
        for output in outputs:
            match = pattern.search(output)
            if match:
                return {"packageName": match.group(1), "activity": match.group(2)}
        return {"packageName": "unknown", "activity": ""}

    def apps(self, serial: str, query: str = "", include_system: bool = False) -> list[dict[str, object]]:
        third_party = self._package_set(serial, ["-3"])
        packages = self._package_set(serial, []) if include_system else set(third_party)
        if query:
            needle = query.lower()
            packages = {package for package in packages if needle in package.lower()}
        return [{"packageName": package, "system": package not in third_party} for package in sorted(packages)]

    def _package_set(self, serial: str, flags: list[str]) -> set[str]:
        text = self.run(["shell", "pm", "list", "packages", *flags], serial=serial).text
        return {line.removeprefix("package:").strip() for line in text.splitlines() if line.startswith("package:")}

    def screenshot(self, serial: str) -> bytes:
        result = self.run(["exec-out", "screencap", "-p"], serial=serial, timeout=15)
        if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            raise CoreError("MEDIA_UNAVAILABLE", "设备截图不可用，请确认设备已解锁。", retryable=True)
        return result.stdout

    def dump_xml(self, serial: str) -> str:
        remote = f"/sdcard/window_dump_layoutsee_{uuid.uuid4().hex}.xml"
        dump = self.run(["shell", "uiautomator", "dump", "--compressed", remote], serial=serial, timeout=15, check=False)
        if dump.returncode != 0:
            dump = self.run(["shell", "uiautomator", "dump", remote], serial=serial, timeout=15, check=False)
        if dump.returncode != 0:
            message = (dump.stderr or dump.stdout).decode("utf-8", errors="replace").strip()
            raise CoreError("CORE_UNAVAILABLE", message or "布局抓取失败。", retryable=True)
        try:
            xml = self.run(["exec-out", "cat", remote], serial=serial, timeout=10).text
        finally:
            self.run(["shell", "rm", "-f", remote], serial=serial, check=False)
        if "<hierarchy" not in xml:
            raise CoreError("CORE_UNAVAILABLE", "设备返回了空布局，请确认页面可被无障碍树读取。", retryable=True)
        return xml

    def logcat_dump(self, serial: str, lines: int = 1200) -> str:
        """一次性 dump 设备日志尾部。用 -d 而不是常驻流：常驻子进程会绕过 run() 这个唯一出口。"""
        count = max(1, min(int(lines), 5000))
        result = self.run(["logcat", "-d", "-v", "threadtime", "-t", str(count)], serial=serial, timeout=20, check=False)
        if result.returncode != 0:
            message = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
            raise CoreError("CORE_UNAVAILABLE", message or "读取设备日志失败。", retryable=True)
        return result.stdout.decode("utf-8", errors="replace")

    def logcat_clear(self, serial: str) -> None:
        # 部分机型即使清空成功也返回非 0（"failed to clear the 'main' log"），不据此报错
        self.run(["logcat", "-c"], serial=serial, timeout=10, check=False)

    def action(self, serial: str, action: str, payload: dict[str, object]) -> dict[str, object]:
        if action == "tap":
            self.run(["shell", "input", "tap", str(int(payload["x"])), str(int(payload["y"]))], serial=serial)
        elif action == "swipe":
            self.run(["shell", "input", "swipe", str(int(payload["fromX"])), str(int(payload["fromY"])), str(int(payload["toX"])), str(int(payload["toY"])), str(int(payload.get("durationMs", 300)))], serial=serial)
        elif action == "input_text":
            text = str(payload.get("text", "")).replace(" ", "%s")
            self.run(["shell", "input", "text", text], serial=serial)
        elif action == "press_key":
            key = str(payload.get("key", "")).upper()
            allowed = {"HOME": "KEYCODE_HOME", "BACK": "KEYCODE_BACK", "RECENTS": "KEYCODE_APP_SWITCH", "POWER": "KEYCODE_POWER", "VOLUME_UP": "KEYCODE_VOLUME_UP", "VOLUME_DOWN": "KEYCODE_VOLUME_DOWN", "ENTER": "KEYCODE_ENTER", "DEL": "KEYCODE_DEL"}
            if key not in allowed:
                raise CoreError("INVALID_ARGUMENT", f"不支持的按键：{key}")
            self.run(["shell", "input", "keyevent", allowed[key]], serial=serial)
        elif action == "start_app":
            package = str(payload.get("packageName", ""))
            activity = str(payload.get("activity", ""))
            if activity:
                self.run(["shell", "am", "start", "-n", f"{package}/{activity}"], serial=serial)
            else:
                self.run(["shell", "monkey", "-p", package, "1"], serial=serial)
        elif action == "stop_app":
            self.run(["shell", "am", "force-stop", str(payload.get("packageName", ""))], serial=serial)
        elif action == "clear_app":
            self._package_command(serial, ["shell", "pm", "clear", self._package_arg(payload)], "清除应用数据失败")
        elif action == "uninstall_app":
            self._package_command(serial, ["shell", "pm", "uninstall", self._package_arg(payload)], "卸载应用失败")
        elif action == "rotate":
            current = self.run(["shell", "settings", "get", "system", "user_rotation"], serial=serial, check=False).text
            try:
                next_rotation = (int(current) + 1) % 4
            except ValueError:
                next_rotation = 1
            self.run(["shell", "settings", "put", "system", "accelerometer_rotation", "0"], serial=serial, check=False)
            self.run(["shell", "settings", "put", "system", "user_rotation", str(next_rotation)], serial=serial, check=False)
        else:
            raise CoreError("INVALID_ARGUMENT", f"不支持的设备动作：{action}")
        return {"action": action, "accepted": True}

    @staticmethod
    def _package_arg(payload: dict[str, object]) -> str:
        package = str(payload.get("packageName", "")).strip()
        # 包名只允许字母数字下划线与点，避免拼进 shell 串后被当成额外参数
        if not package or not re.fullmatch(r"[A-Za-z0-9_.]+", package):
            raise CoreError("INVALID_ARGUMENT", "包名不合法，无法执行包管理动作。")
        return package

    def _package_command(self, serial: str, args: list[str], failure_message: str) -> None:
        # pm clear / pm uninstall 失败时 returncode 仍可能为 0，必须看 Success 字样
        result = self.run(args, serial=serial, timeout=30, check=False)
        text = (result.text + result.stderr.decode("utf-8", errors="replace")).strip()
        if result.returncode != 0 or "Success" not in text:
            raise CoreError("PERMISSION_REQUIRED", f"{failure_message}：{text or '设备未返回结果'}")
