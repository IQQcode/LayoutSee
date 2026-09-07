from __future__ import annotations

import base64
import time
import uuid
from typing import Callable

from . import diagnostics as diagnostics_module
from . import finder
from . import plugin_runtime
from . import summary
from .adb import AdbClient
from .devices import DeviceGate, DeviceRegistry
from .errors import CoreError
from .snapshots import CaptureCoordinator, SnapshotStore
from .xpath import query_record

CATALOG_SCHEMA_VERSION = "1.0"

TOOL_CATALOG: list[dict[str, object]] = [
    {"name": "get_device_info", "kind": "read", "description": "获取当前设备信息、窗口尺寸与连接状态",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_current_app", "kind": "read", "description": "获取设备当前前台应用包名与 Activity",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "capture_layout", "kind": "read", "description": "执行原子布局抓取（冻结→dump→截图→建索引）并返回快照摘要",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_layout", "kind": "read", "description": "获取指定快照的完整节点树与上下文；省略 snapshotId 时返回最新快照",
     "inputSchema": {"type": "object", "properties": {"snapshotId": {"type": "string"}}, "additionalProperties": False}},
    {"name": "query_xpath", "kind": "read", "description": "在快照保存的原始 XML 上执行 XPath 查询并返回 nodeKey 列表",
     "inputSchema": {"type": "object", "required": ["expression"], "properties": {
         "expression": {"type": "string", "maxLength": 512}, "snapshotId": {"type": "string"}}, "additionalProperties": False}},
    {"name": "get_screenshot", "kind": "read", "description": "获取当前设备或指定快照的 PNG 截图（base64）",
     "inputSchema": {"type": "object", "properties": {"snapshotId": {"type": "string"}}, "additionalProperties": False}},
    {"name": "tap", "kind": "write", "description": "在指定坐标或 ref 引用节点上执行点击",
     "inputSchema": {"type": "object", "properties": {
         "x": {"type": "integer", "minimum": 0}, "y": {"type": "integer", "minimum": 0},
         "ref": {"type": "string"}, "durationMs": {"type": "integer", "minimum": 0, "maximum": 2000}},
         "additionalProperties": False}},
    {"name": "swipe", "kind": "write", "description": "执行滑动手势",
     "inputSchema": {"type": "object", "required": ["fromX", "fromY", "toX", "toY"], "properties": {
         "fromX": {"type": "integer"}, "fromY": {"type": "integer"}, "toX": {"type": "integer"},
         "toY": {"type": "integer"}, "durationMs": {"type": "integer", "minimum": 0, "maximum": 5000}},
         "additionalProperties": False}},
    {"name": "input_text", "kind": "write", "description": "向设备发送文本输入",
     "inputSchema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string", "maxLength": 512}}, "additionalProperties": False}},
    {"name": "get_layout_summary", "kind": "read", "description": "生成确定性语义布局摘要，元素携带短 ref 便于引用",
     "inputSchema": {"type": "object", "properties": {"snapshotId": {"type": "string"}}, "additionalProperties": False}},
    {"name": "diagnose_layout", "kind": "read", "description": "对快照执行六类布局异常诊断并返回量化证据",
     "inputSchema": {"type": "object", "properties": {"snapshotId": {"type": "string"}}, "additionalProperties": False}},
    {"name": "find_element", "kind": "read", "description": "按文本、描述或资源 id 在最新快照中检索元素并返回 ref",
     "inputSchema": {"type": "object", "required": ["query"], "properties": {
         "query": {"type": "string", "maxLength": 200}, "snapshotId": {"type": "string"}}, "additionalProperties": False}},
]


BUILTIN_TOOL_NAMES = frozenset(str(item["name"]) for item in TOOL_CATALOG)


def catalog(plugins: object = None) -> dict[str, object]:
    """内置目录恒为 12 项；插件工具追加在后面，用 plugin.{id}.{name} 独立命名空间。"""
    tools = list(TOOL_CATALOG)
    extra = plugin_runtime.plugin_tools(plugins) if plugins is not None else []
    return {"schemaVersion": CATALOG_SCHEMA_VERSION, "tools": tools + extra, "builtinCount": len(TOOL_CATALOG)}


class ToolDispatcher:
    """MCP tools/call 的唯一入口：参数校验、只读门禁与审计统一在此。"""

    def __init__(
        self,
        *,
        adb: AdbClient,
        registry: DeviceRegistry,
        store: SnapshotStore,
        gate: DeviceGate,
        capture: CaptureCoordinator,
        audit,
        plugins=None,
    ) -> None:
        self.adb = adb
        self.registry = registry
        self.store = store
        self.gate = gate
        self.capture = capture
        self.audit = audit
        self.plugins = plugins

    def call(self, device_id: str, tool_name: str, arguments: dict[str, object], *, source: str = "mcp", request_id: str = "", plugin_id: str | None = None) -> dict[str, object]:
        arguments = arguments if isinstance(arguments, dict) else {}
        if tool_name.startswith(plugin_runtime.PLUGIN_TOOL_PREFIX):
            return self._call_declarative(device_id, tool_name, arguments, source, request_id)
        tool = next((item for item in TOOL_CATALOG if item["name"] == tool_name), None)
        if tool is None:
            raise CoreError("INVALID_ARGUMENT", f"未知工具：{tool_name}")
        handler: Callable[..., dict[str, object]] = getattr(self, f"_tool_{tool_name}")
        if tool["kind"] == "write":
            return self._write_guarded(device_id, tool_name, arguments, handler, source, request_id, plugin_id)
        return handler(device_id, arguments)

    def _call_declarative(self, device_id: str, tool_name: str, arguments: dict[str, object], source: str, request_id: str) -> dict[str, object]:
        """声明式组合工具：逐步调用内置工具，能力上限恒等于内置工具集。"""
        plugin_id, tool = plugin_runtime.find_declarative_tool(self.plugins, tool_name)
        scope: dict[str, object] = {"input": arguments}
        last: dict[str, object] = {}
        for index, step in enumerate(tool["steps"]):
            if not isinstance(step, dict):
                raise CoreError("PLUGIN_INVALID", f"第 {index + 1} 步声明非法。")
            if "require" in step:
                if plugin_runtime.resolve_path(scope, str(step["require"])) in (None, "", [], {}, False):
                    fallback = step.get("otherwise") or {}
                    raise CoreError(str(fallback.get("code") or "PLUGIN_INVALID"), str(fallback.get("message") or "插件断言失败。"), details={"pluginId": plugin_id, "step": index + 1})
                continue
            target = str(step.get("call", ""))
            if target not in BUILTIN_TOOL_NAMES:
                raise CoreError("PLUGIN_INVALID", f"插件只能调用内置工具，收到：{target}", details={"pluginId": plugin_id})
            step_args = plugin_runtime.expand(step.get("args") or {}, scope)
            if not isinstance(step_args, dict):
                raise CoreError("PLUGIN_INVALID", f"第 {index + 1} 步参数必须是对象。", details={"pluginId": plugin_id})
            last = self.call(device_id, target, step_args, source="plugin", request_id=request_id, plugin_id=plugin_id)
            if step.get("alias"):
                scope[str(step["alias"])] = last
        return {"tool": tool_name, "pluginId": plugin_id, "steps": len(tool["steps"]), "result": last}

    def _write_guarded(self, device_id, tool_name, arguments, handler, source, request_id, plugin_id=None):
        if self.registry.is_readonly(device_id):
            self.audit.requested(action_id=uuid.uuid4().hex[:12], source=source, device_id=device_id, action_type=tool_name, payload=arguments, request_id=request_id, decision="blocked-readonly", plugin_id=plugin_id)
            raise CoreError("READ_ONLY_MODE", "设备处于只读模式，写操作已被拦截。", details={"tool": tool_name})
        action_id = uuid.uuid4().hex[:12]
        self.audit.requested(action_id=action_id, source=source, device_id=device_id, action_type=tool_name, payload=arguments, request_id=request_id, decision="allowed", plugin_id=plugin_id)
        started = time.monotonic()
        try:
            with self.gate.acquire(device_id):
                result = handler(device_id, arguments)
        except CoreError as error:
            self.audit.result(action_id=action_id, result_code=error.code, duration_ms=int((time.monotonic() - started) * 1000), request_id=request_id)
            raise
        self.audit.result(action_id=action_id, result_code="ok", duration_ms=int((time.monotonic() - started) * 1000), request_id=request_id)
        return result

    def _require_device(self, device_id: str) -> str:
        return self.registry.serial_for(device_id)

    def _record(self, device_id: str) -> dict[str, object]:
        record = self.store.latest_for(device_id)
        if record is None:
            raise CoreError("SNAPSHOT_STALE", "当前没有可用快照，请先调用 capture_layout。")
        return record

    def _record_or_none(self, device_id: str, snapshot_id: object) -> dict[str, object]:
        if snapshot_id:
            return self.store.get(str(snapshot_id))
        return self._record(device_id)

    def _tool_get_device_info(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        serial = self._require_device(device_id)
        descriptor = self.registry.device(device_id)
        size = self.adb.window_size(serial)
        return {
            "deviceId": device_id,
            "platform": "android",
            "serial": descriptor["serial"],
            "model": descriptor.get("model", ""),
            "status": descriptor["status"],
            "readonly": self.registry.is_readonly(device_id),
            "windowSizePx": size,
            "density": self.adb.density(serial),
            "orientation": self.adb.orientation(serial),
        }

    def _tool_get_current_app(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        serial = self._require_device(device_id)
        return self.adb.current_app(serial)

    def _tool_capture_layout(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        record = self.capture.capture(device_id)
        snapshot = record["snapshot"]
        orientation = "landscape" if snapshot["windowSizePx"]["width"] > snapshot["windowSizePx"]["height"] else "portrait"
        return {
            "snapshotId": snapshot["snapshotId"],
            "windowSizePx": snapshot["windowSizePx"],
            "orientation": orientation,
            "nodeCount": len(snapshot["nodes"]),
            "synchronization": snapshot["synchronization"],
            "foreground": snapshot["foreground"],
            "warnings": snapshot["warnings"],
        }

    def _tool_get_layout(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        record = self._record_or_none(device_id, arguments.get("snapshotId"))
        return record["snapshot"]

    def _tool_query_xpath(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        expression = str(arguments.get("expression", ""))
        record = self._record_or_none(device_id, arguments.get("snapshotId"))
        return query_record(record, expression)

    def _tool_get_screenshot(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        if arguments.get("snapshotId"):
            record = self.store.get(str(arguments["snapshotId"]))
            png = record.get("png")
        else:
            serial = self._require_device(device_id)
            png = self.adb.screenshot(serial)
        if not png:
            raise CoreError("MEDIA_UNAVAILABLE", "截图不可用。", retryable=True)
        return {"contentType": "image/png", "base64": base64.b64encode(png).decode("ascii"), "bytes": len(png)}

    def _tool_tap(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        serial = self._require_device(device_id)
        ref = arguments.get("ref")
        if ref:
            record, node_key = self.store.resolve_ref(device_id, str(ref))
            node = next((item for item in record["snapshot"]["nodes"] if item["nodeKey"] == node_key), None)
            if node is None:
                raise CoreError("REF_NOT_FOUND", "ref 对应节点不存在。")
            bounds = node["boundsPx"]
            x = int((bounds["left"] + bounds["right"]) / 2)
            y = int((bounds["top"] + bounds["bottom"]) / 2)
        else:
            x = int(arguments.get("x", -1))
            y = int(arguments.get("y", -1))
            if x < 0 or y < 0:
                raise CoreError("INVALID_ARGUMENT", "tap 需要 x/y 或 ref。")
        self.adb.action(serial, "tap", {"x": x, "y": y, **({"durationMs": arguments["durationMs"]} if arguments.get("durationMs") else {})})
        return {"action": "tap", "x": x, "y": y}

    def _tool_swipe(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        serial = self._require_device(device_id)
        payload = {
            "fromX": int(arguments["fromX"]), "fromY": int(arguments["fromY"]),
            "toX": int(arguments["toX"]), "toY": int(arguments["toY"]),
            "durationMs": int(arguments.get("durationMs", 300)),
        }
        self.adb.action(serial, "swipe", payload)
        return {"action": "swipe", **payload}

    def _tool_input_text(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        serial = self._require_device(device_id)
        text = str(arguments.get("text", ""))
        if not text:
            raise CoreError("INVALID_ARGUMENT", "text 不能为空。")
        self.adb.action(serial, "input_text", {"text": text})
        return {"action": "input_text", "chars": len(text)}

    def _tool_get_layout_summary(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        record = self._record_or_none(device_id, arguments.get("snapshotId"))
        return summary.summarize(record, str(record["snapshot"]["snapshotId"]))

    def _tool_diagnose_layout(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        record = self._record_or_none(device_id, arguments.get("snapshotId"))
        result = diagnostics_module.diagnose(record, str(record["snapshot"]["snapshotId"]))
        findings = self._plugin_findings(record["snapshot"])
        return {**result, "pluginFindings": findings} if findings else result

    def _plugin_findings(self, snapshot: dict[str, object]) -> list[dict[str, object]]:
        """插件诊断规则逐节点求值；总量截断在 50 条，避免规则写太宽把响应撑爆。"""
        findings: list[dict[str, object]] = []
        nodes = snapshot.get("nodes") or []
        for plugin_id, payload in plugin_runtime.contributions(self.plugins, "diagnosticRules"):
            for rule in payload.get("rules") or []:
                if not isinstance(rule, dict):
                    continue
                severity = rule.get("severity") if rule.get("severity") in ("error", "warning", "info") else "info"
                for node in nodes:
                    if len(findings) >= 50:
                        return findings
                    if not plugin_runtime.evaluate_predicate(rule.get("when"), plugin_runtime.node_scope(node, snapshot)):
                        continue
                    finding = {
                        "pluginId": plugin_id,
                        "type": str(rule.get("type", ""))[:40],
                        "severity": severity,
                        "nodeKey": node.get("nodeKey"),
                        "evidence": str(rule.get("evidence", ""))[:200],
                    }
                    if rule.get("suggestion"):
                        finding["suggestion"] = str(rule["suggestion"])[:200]
                    findings.append(finding)
        return findings

    def _tool_find_element(self, device_id: str, arguments: dict[str, object]) -> dict[str, object]:
        record = self._record_or_none(device_id, arguments.get("snapshotId"))
        return finder.find_element(record, str(arguments.get("query", "")))
