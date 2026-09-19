#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LayoutSee Core MCP 直连脚本。

当 MCP 客户端未连接时，直接对本地 Core 的 message 端点发 JSON-RPC。
Core 的响应同步写在 POST body，不走 SSE，所以一个 POST 拿一个结果。
仅依赖 Python 标准库。

用法：
    python3 mcp_call.py --list                        列出工具
    python3 mcp_call.py --devices                     仅列设备
    python3 mcp_call.py capture_layout                调用无参工具
    python3 mcp_call.py get_layout --args '{"snapshotId":"x"}'
    python3 mcp_call.py get_current_app --serial RFCY41B0EVZ

可选：--serial 指定设备，--port 指定端口，--base 指定完整根地址。
"""
import argparse
import json
import urllib.error
import urllib.request

PORT_START = 11663
PORT_ATTEMPTS = 10
TIMEOUT = 8


def _get(url):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def discover_base(explicit_base, explicit_port):
    """返回能响应的 Core 根地址。不带 Origin 头，回环 Host 天然通过校验。"""
    if explicit_base:
        return explicit_base.rstrip("/")
    ports = [explicit_port] if explicit_port else range(PORT_START, PORT_START + PORT_ATTEMPTS)
    for port in ports:
        base = f"http://127.0.0.1:{port}"
        try:
            _get(f"{base}/api/v1/devices")
            return base
        except (urllib.error.URLError, OSError, ValueError):
            continue
    raise SystemExit("未找到运行中的 LayoutSee Core（已探测 11663 到 11672）。请确认桌面应用已打开。")


def list_devices(base):
    envelope = _get(f"{base}/api/v1/devices")
    data = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope
    return data.get("items", []) if isinstance(data, dict) else []


def resolve_device(base, serial):
    items = list_devices(base)
    if not items:
        raise SystemExit("当前无已连设备，请用 adb devices 确认。")
    if serial:
        for item in items:
            if item.get("serial") == serial:
                return item.get("deviceId") or f"android-{serial}"
        raise SystemExit(f"未找到 serial={serial} 的设备。")
    first = items[0]
    return first.get("deviceId") or f"android-{first.get('serial')}"


def rpc(base, device_id, method, params, req_id=1):
    url = f"{base}/mcp/{device_id}/message"
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    return _post(url, payload)


def unwrap(response):
    """从 tools/call 响应里取出工具真正返回的对象。"""
    if "error" in response:
        return response
    result = response.get("result", {})
    content = result.get("content")
    if isinstance(content, list) and content and content[0].get("type") == "text":
        try:
            return json.loads(content[0]["text"])
        except (ValueError, KeyError):
            return content[0].get("text")
    return result


def main():
    parser = argparse.ArgumentParser(description="LayoutSee Core MCP 直连")
    parser.add_argument("tool", nargs="?", help="工具名，如 capture_layout")
    parser.add_argument("--args", help="工具参数 JSON 字符串")
    parser.add_argument("--serial", help="设备 serial，多设备时指定")
    parser.add_argument("--port", type=int, help="Core 端口，默认自动探测")
    parser.add_argument("--base", help="Core 根地址，如 http://127.0.0.1:11663")
    parser.add_argument("--list", action="store_true", help="列出工具")
    parser.add_argument("--devices", action="store_true", help="仅列设备")
    args = parser.parse_args()

    base = discover_base(args.base, args.port)

    if args.devices:
        print(json.dumps(list_devices(base), ensure_ascii=False, indent=2))
        return

    device_id = resolve_device(base, args.serial)

    if args.list:
        resp = rpc(base, device_id, "tools/list", {})
        tools = resp.get("result", {}).get("tools", [])
        print(json.dumps(tools, ensure_ascii=False, indent=2))
        return

    if not args.tool:
        parser.error("需要工具名，或用 --list / --devices")

    try:
        tool_args = json.loads(args.args) if args.args else {}
    except ValueError as exc:
        raise SystemExit(f"--args 不是合法 JSON：{exc}")

    resp = rpc(base, device_id, "tools/call", {"name": args.tool, "arguments": tool_args}, req_id=2)
    print(json.dumps(unwrap(resp), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
