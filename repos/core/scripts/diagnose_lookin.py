"""Lookin 链路诊断脚本：枚举 usbmux 设备 / 端口扫描 / 完整抓取（真机冒烟的人工验证入口）。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
对齐 scripts/diagnose_scrcpy.py 的纯脚本风格。用法（仓库根执行）：

    uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --list
    uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --scan --udid <udid>
    uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --capture --udid <udid> [--out DIR]
    uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --scan --sim        # 模拟器
    uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --capture --sim [--out DIR]

退出码：--list 恒为 0（无 usbmuxd/无设备打印中文提示）；--scan/--capture 无设备或失败为 1。
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from plistlib import UID

sys.path.insert(0, "repos/core/src")
from layoutsee_core.errors import CoreError
from layoutsee_core.ios.client import LookinClient
from layoutsee_core.ios.driver import IOSDeviceDriver
from layoutsee_core.ios.usbmux import UsbmuxClient


def run_list(usbmux_client: UsbmuxClient) -> int:
    if not usbmux_client.available():
        print("未检测到 usbmuxd（仅 macOS 提供），无法枚举 iOS 设备。")
        return 0
    devices = usbmux_client.list_devices()
    if not devices:
        print("usbmuxd 可用，但当前没有通过 USB 连接的 iOS 设备。")
        return 0
    for entry in devices:
        print(json.dumps({"udid": entry["udid"], "deviceId": entry["deviceId"]}, ensure_ascii=False))
    return 0


def run_scan(usbmux_client: UsbmuxClient, udid: str) -> int:
    result: dict[str, object] = {}
    found = False
    for port in IOSDeviceDriver.USB_PORTS:
        entry: dict[str, object]
        try:
            stream = usbmux_client.connect(udid, port)
        except CoreError as error:
            result[str(port)] = {"stage": "connect", "error": error.code, "message": error.message}
            continue
        except OSError as error:  # 裸 socket 错误统一归类，不让脚本崩溃
            result[str(port)] = {"stage": "connect", "error": "LOOKIN_UNAVAILABLE", "message": f"与设备端口 {port} 通信失败：{error}"}
            continue
        lookin = LookinClient(stream)
        try:
            version = lookin.ping()
            info = lookin.app_info()
            data = info.get("data") if isinstance(info.get("data"), dict) else {}
            entry = {
                "bundleId": data.get("appBundleIdentifier") or "",
                "appName": data.get("appName") or "",
                "background": info.get("appIsInBackground"),
                "serverVersion": version,
            }
            found = True
        except CoreError as error:
            entry = {"stage": "request", "error": error.code, "message": error.message}
        except OSError as error:
            entry = {"stage": "request", "error": "LOOKIN_UNAVAILABLE", "message": f"与设备端口 {port} 通信失败：{error}"}
        finally:
            try:
                stream.close()
            except OSError:
                pass
        result[str(port)] = entry
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not found:
        print("扫描完成：未发现任何 Lookin App（确认被测 App 已集成 LookinServer 且 USB 连接正常）。")
        return 1
    return 0


def _json_default(value: object) -> object:
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, UID):
        return f"UID({value.data})"
    return str(value)


def run_scan_sim() -> int:
    """扫描本机 loopback 模拟器端口（47164-47169）：连接被拒的端口记为 closed，降低噪音。"""
    driver = IOSDeviceDriver()
    result: dict[str, object] = {}
    found = False
    for port in driver.SIM_PORTS:
        stream = None
        try:
            stream = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        except OSError:
            result[str(port)] = {"stage": "connect", "closed": True}
            continue
        try:
            lookin = LookinClient(stream)
            version = lookin.ping()
            info = lookin.app_info()
            data = info.get("data") if isinstance(info.get("data"), dict) else {}
            foreground = info.get("appIsInBackground") is False
            found = found or foreground
            result[str(port)] = {
                "bundleId": data.get("appBundleIdentifier") or "",
                "appName": data.get("appName") or "",
                "background": info.get("appIsInBackground"),
                "serverVersion": version,
            }
        except CoreError as error:
            result[str(port)] = {"stage": "request", "error": error.code, "message": error.message}
        except OSError as error:
            result[str(port)] = {"stage": "request", "error": "LOOKIN_UNAVAILABLE", "message": str(error)}
        finally:
            try:
                stream.close()
            except OSError:
                pass
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not found:
        print("模拟器扫描完成：未发现可连接的 Lookin App（确认模拟器内 App 正在前台运行，且已退出 Lookin 官方客户端）。")
        return 1
    return 0


def run_capture_sim(out_dir: Path) -> int:
    """模拟器抓取：先扫描端口选前台 App，再复用 capture_debug。"""
    driver = IOSDeviceDriver()
    serial: str | None = None
    for port in driver.SIM_PORTS:
        probe: list[dict[str, object]] = []
        selected = driver.probe_port(driver.SIMULATOR_SERIAL_PREFIX + str(port), port, probe)
        if selected is not None:
            try:
                selected[0].stream.close()
            except OSError:
                pass
            serial = driver.SIMULATOR_SERIAL_PREFIX + str(port)
            break
    if serial is None:
        print("模拟器抓取失败：未找到可连接的前台 Lookin App（App 未运行 / 未集成 / Lookin 官方客户端占用中）。")
        return 1
    return run_capture(None, serial, out_dir)  # 模拟器路径不经过 usbmux，传 None


def run_capture(usbmux_client: UsbmuxClient | None, udid: str, out_dir: Path) -> int:
    """完整抓取：复用 IOSDeviceDriver.capture_debug（capture() 结果 + 解码后 raw 树）。"""
    ios_driver = IOSDeviceDriver(usbmux_client)
    try:
        capture = ios_driver.capture_debug(udid)
    except CoreError as error:
        print(f"抓取失败：[{error.code}] {error.message}")
        attempts = error.details.get("attempts")
        if attempts:
            print(json.dumps(attempts, ensure_ascii=False, indent=2, default=_json_default))
        return 1
    except OSError as error:
        print(f"抓取失败：[LOOKIN_UNAVAILABLE] 与设备通信失败：{error}")
        return 1

    raw = capture.get("raw") if isinstance(capture.get("raw"), dict) else {}
    window_size = capture.get("window_size") if isinstance(capture.get("window_size"), dict) else {}
    warnings = list(capture.get("warnings") or [])
    out_dir.mkdir(parents=True, exist_ok=True)
    xml_path = out_dir / f"lookin-{udid}.xml"
    tree_path = out_dir / f"lookin-{udid}-tree.json"
    xml_path.write_text(str(capture.get("xml")), encoding="utf-8")
    tree = {
        "app": capture.get("app"),
        "windowSize": window_size,
        "raw": raw,  # 解码后的层级树与属性详情原始结构，供真机校准键名
        "warnings": warnings,
    }
    tree_path.write_text(
        json.dumps(tree, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(f"窗口尺寸：{window_size.get('width')}x{window_size.get('height')}")
    print(f"XML：{xml_path}")
    print(f"树 JSON：{tree_path}")
    if warnings:
        print("警告：")
        for warning in warnings:
            print(f"  - {warning}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Lookin 链路诊断（枚举 / 扫描 / 抓取）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="列出 usbmux 设备（udid、DeviceID）")
    group.add_argument("--scan", action="store_true", help="扫描 47175-47179 端口的 Lookin App，输出 JSON")
    group.add_argument("--capture", action="store_true", help="完整抓取，输出 XML 与解码后的树 JSON")
    parser.add_argument("--sim", action="store_true", help="针对模拟器（本机 loopback 47164-47169）执行 --scan/--capture")
    parser.add_argument("--udid", help="设备 UDID（真机 --scan/--capture 必填）")
    parser.add_argument("--out", default=".", help="输出目录（--capture 用，默认当前目录）")
    args = parser.parse_args()

    if args.sim:
        if args.scan:
            return run_scan_sim()
        if args.capture:
            return run_capture_sim(Path(args.out))
        print("--sim 需要与 --scan 或 --capture 搭配使用。")
        return 1

    usbmux_client = UsbmuxClient()
    if args.list:
        return run_list(usbmux_client)
    if not args.udid:
        print("缺少 --udid 参数（可用 --list 查看设备 UDID）。")
        return 1
    if not usbmux_client.available():
        print("未检测到 usbmuxd（仅 macOS 提供），请确认 macOS 且 iOS 设备已通过 USB 连接。")
        return 1
    if args.scan:
        return run_scan(usbmux_client, args.udid)
    return run_capture(usbmux_client, args.udid, Path(args.out))


if __name__ == "__main__":
    sys.exit(main())
