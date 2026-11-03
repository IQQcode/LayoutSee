#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LayoutSee 环境体检与 adbPath 写入脚本。

仅依赖 Python 标准库；子进程一律 argv 列表调用，网络只访问回环地址的本地 Core。

用法：
    python3 env_check.py check [--json] [--port N]   体检（exit 0 全绿 / 1 有缺口）
    python3 env_check.py set-adb <adb 路径>          写入 settings.json 的 adbPath（App 未运行时）

settings.json 位置遵循 Core 约定：LAYOUTSEE_DATA_DIR 覆盖，否则 ~/Library/Application Support/LayoutSee。
"""
import argparse
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

PORT_START = 11663
PORT_ATTEMPTS = 10
HTTP_TIMEOUT = 8
SUBPROCESS_TIMEOUT = 20

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# 与 repos/core/src/layoutsee_core/adb.py 的 ADB_CANDIDATE_PATHS 保持一致
ADB_CANDIDATE_PATHS = [
    "/opt/local/bin/adb",
    "/opt/homebrew/bin/adb",
    "/usr/local/bin/adb",
    "~/Library/Android/sdk/platform-tools/adb",
    "~/Android/Sdk/platform-tools/adb",
]

ADB_MISSING_HINT = "未找到 adb。可运行 brew install android-platform-tools，或安装后用 set-adb 指定路径。"

EXIT_OK = 0
EXIT_GAP = 1
EXIT_SET_REFUSED = 2
EXIT_SET_INVALID = 3


def data_dir():
    override = os.environ.get("LAYOUTSEE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "LayoutSee"


def settings_path():
    return data_dir() / "settings.json"


def _assert_loopback(url):
    """只服务本机 Core：协议限 http(s)，host 字面量与 DNS 解析结果都必须是回环地址。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http(s) 协议，收到: {parsed.scheme}")
    hostname = parsed.hostname or ""
    if hostname.lower() not in LOOPBACK_HOSTS:
        raise ValueError(f"仅允许访问回环地址，收到 host: {hostname}")
    default_port = 443 if parsed.scheme == "https" else 80
    for info in socket.getaddrinfo(hostname, parsed.port or default_port, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_loopback:
            raise ValueError(f"主机 {hostname} 解析出非回环地址 {ip}，已拒绝请求")


def http_get_json(url):
    _assert_loopback(url)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run(argv, timeout=SUBPROCESS_TIMEOUT):
    """argv 列表调用子进程（Mimosa 约束：禁 shell 拼接，统一走本入口）；返回 (returncode, stdout, stderr)。"""
    try:
        # 显式 shell=False：argv 恒为列表（调用点全部是字面量，或 settings 配置的 adb 可执行路径），不经过 shell 解析
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, shell=False)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return None, "", f"命令不存在: {argv[0]}"
    except subprocess.TimeoutExpired:
        return None, "", f"命令超时: {' '.join(argv)}"


# ---------------------------------------------------------------- 体检项


def check_layoutsee_app():
    for base in (Path("/Applications"), Path.home() / "Applications"):
        candidate = base / "LayoutSee.app"
        if candidate.exists():
            return {"status": "ok", "installed": True, "path": str(candidate)}
    return {
        "status": "missing",
        "installed": False,
        "path": None,
        "hint": "未找到 LayoutSee.app，请从官网 https://layoutsee-site.vercel.app/download.html 下载安装",
    }


def check_core(explicit_port=None):
    ports = [explicit_port] if explicit_port else range(PORT_START, PORT_START + PORT_ATTEMPTS)
    for port in ports:
        base = f"http://127.0.0.1:{port}"
        try:
            envelope = http_get_json(f"{base}/api/v1/devices")
        except (urllib.error.URLError, OSError, ValueError):
            continue
        data = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope
        items = data.get("items", []) if isinstance(data, dict) else []
        devices = [
            {key: item[key] for key in ("deviceId", "serial", "platform", "name", "state") if key in item}
            for item in items
            if isinstance(item, dict)
        ]
        return {"status": "running", "base": base, "deviceCount": len(devices), "devices": devices}
    return {
        "status": "stopped",
        "base": None,
        "deviceCount": 0,
        "devices": [],
        "hint": "Core 未运行，请打开 LayoutSee 桌面应用（源码形态可 npm run dev:web）",
    }


def check_settings():
    path = settings_path()
    if not path.exists():
        return {"status": "absent", "path": str(path), "adbPath": None}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "unreadable", "path": str(path), "adbPath": None}
    adb_path = raw.get("adbPath") if isinstance(raw, dict) else None
    return {"status": "ok", "path": str(path), "adbPath": adb_path if isinstance(adb_path, str) and adb_path else None}


def parse_adb_devices(out):
    rows = []
    for line in (out or "").splitlines()[1:]:
        line = line.strip()
        if "\t" not in line:
            continue
        serial, rest = line.split("\t", 1)
        rows.append({"serial": serial.strip(), "state": rest.split(" ", 1)[0].strip()})
    return rows


def check_adb(configured_path):
    result = {
        "status": "missing",
        "path": None,
        "source": None,
        "version": None,
        "devices": [],
        "configured": configured_path or None,
    }
    candidates = []
    if configured_path:
        candidates.append(("settings", os.path.expanduser(configured_path)))
    which = shutil.which("adb")
    if which:
        candidates.append(("PATH", which))
    for raw in ADB_CANDIDATE_PATHS:
        candidates.append(("candidate", os.path.expanduser(raw)))
    for source, path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            result.update({"status": "ok", "path": path, "source": source})
            break
    if result["status"] != "ok":
        result["hint"] = ADB_MISSING_HINT
        return result
    code, out, _err = run([result["path"], "version"])
    if code == 0 and out:
        result["version"] = out.splitlines()[0].strip()
    code, out, _err = run([result["path"], "devices", "-l"])
    result["devices"] = parse_adb_devices(out)
    if any(row["state"] == "unauthorized" for row in result["devices"]):
        result["hint"] = "检测到 unauthorized 设备：请在手机上确认 USB 调试授权弹窗"
    elif not result["devices"]:
        result["hint"] = "adb 可用但当前无设备：手机开启开发者选项与 USB 调试，数据线连接并确认授权"
    return result


def check_ios_toolchain():
    result = {"xcode": None, "simctl": False, "runtimes": [], "booted": [], "hints": []}
    code, out, _err = run(["xcodebuild", "-version"])
    if code == 0 and out:
        result["xcode"] = out.splitlines()[0].strip()
    else:
        result["hints"].append("未检测到完整 Xcode（xcodebuild 不可用），模拟器截图依赖 Xcode，请从 App Store 安装")
    code, out, _err = run(["xcrun", "simctl", "list", "runtimes", "--json"])
    if code == 0 and out:
        result["simctl"] = True
        try:
            data = json.loads(out)
            result["runtimes"] = [
                str(runtime.get("name") or runtime.get("identifier") or "")
                for runtime in data.get("runtimes", [])
                if isinstance(runtime, dict)
            ]
            result["runtimes"] = [name for name in result["runtimes"] if name]
        except ValueError:
            pass
        if not result["runtimes"]:
            result["hints"].append("未安装任何模拟器 runtime：Xcode → Settings → Platforms 下载所需 iOS runtime")
    else:
        result["hints"].append("simctl 不可用（需要 Xcode 或 Command Line Tools）")
    code, out, _err = run(["xcrun", "simctl", "list", "devices", "booted", "--json"])
    if code == 0 and out:
        try:
            data = json.loads(out)
            for devices in (data.get("devices") or {}).values():
                for device in devices or []:
                    if isinstance(device, dict) and device.get("state") == "Booted" and device.get("name"):
                        result["booted"].append(str(device["name"]))
        except ValueError:
            pass
    return result


def check_cocoapods():
    code, out, _err = run(["pod", "--version"])
    if code == 0 and out:
        return {"status": "ok", "version": out.strip().splitlines()[0]}
    return {
        "status": "missing",
        "version": None,
        "hint": "未安装 CocoaPods（gem install cocoapods 或 brew install cocoapods）；仅 iOS 工程走 CocoaPods 集成时需要",
    }


def check_lookin_conflict():
    code, out, _err = run(["pgrep", "-x", "Lookin"])
    if code == 0 and out.strip():
        return {
            "status": "conflict",
            "running": True,
            "hint": "官方 Lookin 客户端正在运行：LookinServer 单客户端独占，请退出 Lookin 后再连 LayoutSee",
        }
    return {"status": "ok", "running": False}


def summarize(checks):
    adb = checks["adb"]
    core = checks["core"]
    ios = checks["iosToolchain"]
    android_ready = adb.get("status") == "ok"
    ios_ready = (
        bool(ios.get("xcode"))
        and ios.get("simctl") is True
        and bool(ios.get("runtimes"))
        and checks["lookinConflict"].get("status") == "ok"
    )
    actions = []
    if not checks["layoutseeApp"].get("installed"):
        actions.append("安装 LayoutSee 桌面应用（官网下载 DMG）")
    if core.get("status") != "running":
        actions.append("打开 LayoutSee 桌面应用以启动 Core")
    if adb.get("status") != "ok":
        actions.append("安装 ADB：brew install android-platform-tools（或安装后用 set-adb 指定已有路径）")
    elif not adb.get("devices"):
        actions.append("连接 Android 设备：开启开发者选项与 USB 调试，数据线连接并在手机上确认授权")
    if any(row.get("state") == "unauthorized" for row in adb.get("devices", [])):
        actions.append("在手机上确认 USB 调试授权弹窗（当前设备 unauthorized）")
    if not ios.get("xcode"):
        actions.append("安装 Xcode（iOS 支持需要）")
    if ios.get("simctl") and not ios.get("runtimes"):
        actions.append("在 Xcode → Settings → Platforms 下载 iOS 模拟器 runtime")
    if checks["lookinConflict"].get("status") == "conflict":
        actions.append("退出官方 Lookin 客户端（LookinServer 单客户端独占）")
    if checks["cocoapods"].get("status") != "ok":
        actions.append("如需 CocoaPods 集成 LookinServer：安装 CocoaPods（gem install cocoapods 或 brew install cocoapods）")
    return {"androidReady": android_ready, "iosReady": ios_ready, "actions": actions}


# ---------------------------------------------------------------- 输出


def print_report(result):
    checks = result["checks"]
    app = checks["layoutseeApp"]
    core = checks["core"]
    adb = checks["adb"]
    ios = checks["iosToolchain"]
    pods = checks["cocoapods"]
    lookin = checks["lookinConflict"]

    print("LayoutSee 环境体检")
    print(f"- 应用: {'已安装 ' + app['path'] if app.get('installed') else app.get('hint', '未安装')}")
    if core.get("status") == "running":
        print(f"- Core: 运行中（{core['base']}），在线设备 {core['deviceCount']} 台")
        for item in core["devices"]:
            label = item.get("deviceId", "?")
            extra = f"（serial={item['serial']}）" if item.get("serial") else ""
            print(f"  - {label}{extra}")
    else:
        print(f"- Core: {core.get('hint', '未运行')}")

    if adb.get("status") == "ok":
        source = {"settings": "设置指定", "PATH": "PATH", "candidate": "候选路径"}.get(adb["source"], adb["source"])
        version = f"，{adb['version']}" if adb.get("version") else ""
        print(f"- ADB: {adb['path']}（{source}{version}）")
        for row in adb["devices"]:
            print(f"  - 设备 {row['serial']}: {row['state']}")
        if adb.get("hint"):
            print(f"  - {adb['hint']}")
    else:
        configured = f"（settings 指定 {adb['configured']}，但该路径不可用）" if adb.get("configured") else ""
        print(f"- ADB: {adb.get('hint', '未找到')}{configured}")

    print(f"- iOS 工具链: {ios['xcode'] or '未检测到 Xcode'}")
    if ios.get("simctl"):
        runtimes = "、".join(ios["runtimes"]) if ios["runtimes"] else "无已装 runtime"
        booted = f"；booted: {'、'.join(ios['booted'])}" if ios["booted"] else ""
        print(f"  - 模拟器 runtime: {runtimes}{booted}")
    for hint in ios.get("hints", []):
        print(f"  - {hint}")

    print(f"- CocoaPods: {pods['version'] if pods.get('status') == 'ok' else pods.get('hint', '未安装')}")
    print(f"- 官方 Lookin: {'运行中（端口冲突，请退出）' if lookin.get('running') else '未运行'}")

    summary = result["summary"]
    print(f"- 结论: Android {'就绪' if summary['androidReady'] else '未就绪'}，iOS 环境{'就绪' if summary['iosReady'] else '未就绪'}（LookinServer 集成另见 layout-lookin-server skill）")
    if summary["actions"]:
        print("- 建议动作:")
        for action in summary["actions"]:
            print(f"  - {action}")


# ---------------------------------------------------------------- 子命令


def cmd_check(args):
    settings = check_settings()
    checks = {
        "layoutseeApp": check_layoutsee_app(),
        "core": check_core(args.port),
        "settings": settings,
        "adb": check_adb(settings.get("adbPath")),
        "iosToolchain": check_ios_toolchain(),
        "cocoapods": check_cocoapods(),
        "lookinConflict": check_lookin_conflict(),
    }
    result = {"checks": checks, "summary": summarize(checks)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)
    all_green = checks["adb"]["status"] == "ok" and checks["core"]["status"] == "running"
    return EXIT_OK if all_green else EXIT_GAP


def is_app_running():
    for pattern in ("LayoutSee.app", "layoutsee-core", "layoutsee_core"):
        code, out, _err = run(["pgrep", "-f", pattern])
        if code == 0 and out.strip():
            return True
    return False


def cmd_set_adb(raw_path):
    expanded = os.path.expanduser(raw_path.strip())
    if not os.path.isfile(expanded) or not os.access(expanded, os.X_OK):
        print(json.dumps(
            {"status": "invalid", "path": expanded, "hint": "路径不存在或没有可执行权限"},
            ensure_ascii=False,
        ))
        return EXIT_SET_INVALID
    if is_app_running():
        print(json.dumps(
            {
                "status": "refused",
                "hint": "LayoutSee 正在运行，settings.json 可能被运行中的 Core 覆盖；请先退出应用，或直接在应用设置页指定 adb 路径",
            },
            ensure_ascii=False,
        ))
        return EXIT_SET_REFUSED
    path = settings_path()
    payload = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
        except (OSError, ValueError):
            payload = {}
    payload["adbPath"] = expanded
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    print(json.dumps({"status": "written", "path": str(path), "adbPath": expanded}, ensure_ascii=False))
    return EXIT_OK


def main():
    parser = argparse.ArgumentParser(description="LayoutSee 环境体检与 adbPath 写入")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="环境体检")
    p_check.add_argument("--json", action="store_true", help="输出 JSON（默认人读报告）")
    p_check.add_argument("--port", type=int, help="Core 端口，默认自动探测 11663-11672")
    p_set = sub.add_parser("set-adb", help="写入 settings.json 的 adbPath（LayoutSee 未运行时）")
    p_set.add_argument("path", help="adb 可执行文件路径")
    args = parser.parse_args()
    if args.command == "check":
        raise SystemExit(cmd_check(args))
    raise SystemExit(cmd_set_adb(args.path))


if __name__ == "__main__":
    main()
