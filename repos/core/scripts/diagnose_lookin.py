"""Lookin 链路诊断脚本：枚举 usbmux 设备 / 端口扫描 / 完整抓取（真机冒烟的人工验证入口）。

对齐 scripts/diagnose_scrcpy.py 的纯脚本风格。用法（仓库根执行）：

    uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --list
    uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --scan --udid <udid>
    uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --capture --udid <udid> [--out DIR]

退出码：--list 恒为 0（无 usbmuxd/无设备打印中文提示）；--scan/--capture 无设备或失败为 1。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from plistlib import UID

sys.path.insert(0, "repos/core/src")
from layoutsee_core.errors import CoreError
from layoutsee_core.ios.client import LookinClient
from layoutsee_core.ios.driver import IOSDeviceDriver, build_xml, flatten_app_info, round_px
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


def run_capture(usbmux_client: UsbmuxClient, udid: str, out_dir: Path) -> int:
    ios_driver = IOSDeviceDriver(usbmux_client)
    attempts: list[dict[str, object]] = []
    selected: tuple[LookinClient, dict[str, object], int] | None = None
    for port in ios_driver.USB_PORTS:
        selected = ios_driver.probe_port(udid, port, attempts)
        if selected is not None:
            break
    if selected is None:
        print("未找到前台运行的 Lookin App（被测 App 需集成 LookinServer 且处于前台）。")
        print(json.dumps(attempts, ensure_ascii=False, indent=2, default=_json_default))
        return 1
    lookin_client, info, port = selected
    try:
        hierarchy = lookin.hierarchy()
        warnings = list(hierarchy.get("warnings") or [])
        details: dict[str, object] = {"attrGroupsByOid": {}, "batches": [], "droppedImageFieldCount": 0}
        try:
            details = lookin.hierarchy_details()
        except CoreError as error:
            warnings.append(f"属性拉取失败（已降级）：{error.message}")
        warnings.extend(details.get("warnings") or [])
        app = flatten_app_info(info)
        app["port"] = port
        scale = float(app.get("screenScale") or 1)
        attr_groups = details.get("attrGroupsByOid") if isinstance(details.get("attrGroupsByOid"), dict) else {}
        xml = build_xml(hierarchy.get("data"), scale, attr_groups, warnings)
        window_size = {
            "width": round_px(float(app.get("screenWidth") or 0) * scale),
            "height": round_px(float(app.get("screenHeight") or 0) * scale),
        }
    except CoreError as error:
        print(f"抓取失败：[{error.code}] {error.message}")
        return 1
    finally:
        try:
            lookin_client.stream.close()
        except OSError:
            pass

    out_dir.mkdir(parents=True, exist_ok=True)
    xml_path = out_dir / f"lookin-{udid}.xml"
    tree_path = out_dir / f"lookin-{udid}-tree.json"
    xml_path.write_text(xml, encoding="utf-8")
    tree = {
        "app": app,
        "port": port,
        "hierarchy": hierarchy.get("data"),
        "details": details,
        "warnings": warnings,
    }
    tree_path.write_text(
        json.dumps(tree, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(f"窗口尺寸：{window_size['width']}x{window_size['height']}")
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
    parser.add_argument("--udid", help="设备 UDID（--scan/--capture 必填）")
    parser.add_argument("--out", default=".", help="输出目录（--capture 用，默认当前目录）")
    args = parser.parse_args()

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
