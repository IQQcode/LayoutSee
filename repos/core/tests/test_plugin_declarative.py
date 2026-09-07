from __future__ import annotations

import unittest
from contextlib import contextmanager

from layoutsee_core import plugin_runtime
from layoutsee_core.errors import CoreError
from layoutsee_core.mcp_catalog import TOOL_CATALOG, ToolDispatcher, catalog

TAP_CENTER_TOOL = {
    "name": "tap_bottom",
    "kind": "write",
    "description": "点击屏幕底部中线",
    "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}}},
    "steps": [
        {"call": "get_device_info", "alias": "info"},
        {"require": "$.info.windowSizePx.height", "otherwise": {"code": "MEDIA_UNAVAILABLE", "message": "缺少窗口尺寸"}},
        {"call": "tap", "args": {"x": "$.input.x", "y": "$.info.windowSizePx.height"}},
    ],
}

NARROW_RULE = {
    "type": "narrow_touch_target",
    "severity": "warning",
    "when": {"all": [{"field": "width", "op": "lt", "value": 40}, {"field": "node.clickable", "op": "eq", "value": True}]},
    "evidence": "可点击区域宽度不足 40px",
    "suggestion": "扩大触控区域",
}


class StubPlugins:
    """只提供 index / read_contribution 两个 PluginRegistry 契约方法。"""

    def __init__(self, tools: list[dict] | None = None, rules: list[dict] | None = None) -> None:
        self.tools = tools or []
        self.rules = rules or []

    def index(self, *, refresh: bool = False) -> dict[str, object]:
        return {"items": [{"id": "demo", "status": "ready"}]}

    def read_contribution(self, plugin_id: str, kind: str) -> dict[str, object] | None:
        if plugin_id != "demo":
            return None
        if kind == "mcpTools":
            return {"schemaVersion": "1.0", "tools": self.tools}
        if kind == "diagnosticRules":
            return {"schemaVersion": "1.0", "rules": self.rules}
        return None


class StubAdb:
    def __init__(self) -> None:
        self.actions: list[tuple[str, dict]] = []

    def window_size(self, serial: str) -> dict[str, int]:
        return {"width": 1080, "height": 2400}

    def density(self, serial: str) -> int:
        return 3

    def orientation(self, serial: str) -> str:
        return "portrait"

    def action(self, serial: str, action_type: str, payload: dict) -> dict:
        self.actions.append((action_type, payload))
        return {"ok": True}


class StubDeviceRegistry:
    def is_readonly(self, device_id: str) -> bool:
        return False

    def serial_for(self, device_id: str) -> str:
        return "serial-1"

    def device(self, device_id: str) -> dict[str, object]:
        return {"serial": "serial-1", "model": "Pixel", "status": "ready"}


class StubGate:
    @contextmanager
    def acquire(self, device_id: str):
        yield


class StubAudit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def requested(self, **kwargs) -> None:
        self.events.append(kwargs)

    def result(self, **kwargs) -> None:
        return None


def build_dispatcher(plugins: StubPlugins) -> tuple[ToolDispatcher, StubAdb, StubAudit]:
    adb, audit = StubAdb(), StubAudit()
    dispatcher = ToolDispatcher(adb=adb, registry=StubDeviceRegistry(), store=None, gate=StubGate(), capture=None, audit=audit, plugins=plugins)
    return dispatcher, adb, audit


class DeclarativeToolTest(unittest.TestCase):
    def test_catalog_keeps_builtin_count_and_prefixes_plugin_tools(self) -> None:
        payload = catalog(StubPlugins(tools=[TAP_CENTER_TOOL]))
        self.assertEqual(payload["builtinCount"], len(TOOL_CATALOG))
        self.assertEqual(len(TOOL_CATALOG), 12)
        names = [item["name"] for item in payload["tools"]]
        self.assertEqual(names[:12], [item["name"] for item in TOOL_CATALOG])
        self.assertEqual(names[12], "plugin.demo.tap_bottom")
        self.assertEqual(payload["tools"][12]["pluginId"], "demo")

    def test_steps_resolve_references_and_audit_records_plugin(self) -> None:
        dispatcher, adb, audit = build_dispatcher(StubPlugins(tools=[TAP_CENTER_TOOL]))
        result = dispatcher.call("android-1", "plugin.demo.tap_bottom", {"x": 540}, source="mcp", request_id="req-1")
        self.assertEqual(result["pluginId"], "demo")
        self.assertEqual(result["steps"], 3)
        self.assertEqual(adb.actions, [("tap", {"x": 540, "y": 2400})])
        write_event = next(event for event in audit.events if event["action_type"] == "tap")
        self.assertEqual(write_event["source"], "plugin")
        self.assertEqual(write_event["plugin_id"], "demo")

    def test_require_failure_raises_declared_code(self) -> None:
        tool = {**TAP_CENTER_TOOL, "steps": [{"require": "$.input.missing", "otherwise": {"code": "AMBIGUOUS_ELEMENT", "message": "未唯一命中"}}]}
        dispatcher, adb, _ = build_dispatcher(StubPlugins(tools=[tool]))
        with self.assertRaises(CoreError) as caught:
            dispatcher.call("android-1", "plugin.demo.tap_bottom", {})
        self.assertEqual(caught.exception.code, "AMBIGUOUS_ELEMENT")
        self.assertEqual(adb.actions, [])

    def test_only_builtin_tools_are_callable(self) -> None:
        for target in ("shell_exec", "plugin.demo.tap_bottom"):
            tool = {**TAP_CENTER_TOOL, "steps": [{"call": target}]}
            dispatcher, _, _ = build_dispatcher(StubPlugins(tools=[tool]))
            with self.assertRaises(CoreError) as caught:
                dispatcher.call("android-1", "plugin.demo.tap_bottom", {})
            self.assertEqual(caught.exception.code, "PLUGIN_INVALID")

    def test_unknown_and_oversized_tools_rejected(self) -> None:
        dispatcher, _, _ = build_dispatcher(StubPlugins(tools=[]))
        with self.assertRaises(CoreError) as missing:
            dispatcher.call("android-1", "plugin.demo.nope", {})
        self.assertEqual(missing.exception.code, "PLUGIN_NOT_FOUND")
        oversized = {**TAP_CENTER_TOOL, "steps": [{"call": "get_device_info"}] * 7}
        dispatcher, _, _ = build_dispatcher(StubPlugins(tools=[oversized]))
        with self.assertRaises(CoreError) as too_many:
            dispatcher.call("android-1", "plugin.demo.tap_bottom", {})
        self.assertEqual(too_many.exception.code, "PLUGIN_INVALID")

    def test_diagnostic_rules_attach_findings(self) -> None:
        dispatcher, _, _ = build_dispatcher(StubPlugins(rules=[NARROW_RULE]))
        snapshot = {
            "windowSizePx": {"width": 1080, "height": 2400},
            "nodes": [
                {"nodeKey": "n1", "clickable": True, "boundsPx": {"left": 0, "top": 0, "right": 24, "bottom": 24}},
                {"nodeKey": "n2", "clickable": True, "boundsPx": {"left": 0, "top": 0, "right": 200, "bottom": 60}},
                {"nodeKey": "n3", "clickable": False, "boundsPx": {"left": 0, "top": 0, "right": 10, "bottom": 10}},
            ],
        }
        findings = dispatcher._plugin_findings(snapshot)
        self.assertEqual([item["nodeKey"] for item in findings], ["n1"])
        self.assertEqual(findings[0]["pluginId"], "demo")
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertEqual(findings[0]["suggestion"], "扩大触控区域")


class ExpressionTest(unittest.TestCase):
    def test_expand_replaces_whole_string_only(self) -> None:
        scope = {"input": {"text": "登录"}, "hit": {"ref": "e3"}}
        self.assertEqual(plugin_runtime.expand({"query": "$.input.text", "note": "前缀 $.input.text"}, scope), {"query": "登录", "note": "前缀 $.input.text"})
        self.assertIsNone(plugin_runtime.resolve_path(scope, "$.hit.missing.deep"))

    def test_conditions_cover_operators(self) -> None:
        scope = {"node": {"text": "确认提交", "tags": ["a", "b"]}, "width": 30}
        self.assertTrue(plugin_runtime.evaluate_condition({"field": "node.text", "op": "contains", "value": "提交"}, scope))
        self.assertTrue(plugin_runtime.evaluate_condition({"field": "node.tags", "op": "contains", "value": "b"}, scope))
        self.assertTrue(plugin_runtime.evaluate_condition({"field": "width", "op": "lte", "value": 30}, scope))
        self.assertTrue(plugin_runtime.evaluate_condition({"field": "node.missing", "op": "empty"}, scope))
        self.assertFalse(plugin_runtime.evaluate_condition({"field": "node.text", "op": "gt", "value": 3}, scope))
        self.assertFalse(plugin_runtime.evaluate_condition({"field": "width", "op": "regex", "value": "x"}, scope))
        self.assertFalse(plugin_runtime.evaluate_predicate({"none": []}, scope))


if __name__ == "__main__":
    unittest.main()
