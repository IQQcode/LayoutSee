"""插件声明式运行时：表达式求值、组合工具与诊断规则。

安全前提：Core 不执行任何第三方 Python。插件只能提交「调用哪个内置工具、断言哪个字段」的声明，
由本模块解释执行，因此能力上限恒等于内置工具集。
"""

from __future__ import annotations

from typing import Any

from .errors import CoreError

PLUGIN_TOOL_PREFIX = "plugin."
MAX_STEPS = 6
COMPARISONS = {
    "eq": lambda left, right: left == right,
    "ne": lambda left, right: left != right,
    "lt": lambda left, right: _numeric(left) < _numeric(right),
    "lte": lambda left, right: _numeric(left) <= _numeric(right),
    "gt": lambda left, right: _numeric(left) > _numeric(right),
    "gte": lambda left, right: _numeric(left) >= _numeric(right),
}


def _numeric(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CoreError("INVALID_ARGUMENT", "比较运算只接受数字。")
    return float(value)


def resolve_path(scope: dict[str, Any], expression: str) -> Any:
    """解析 `$.alias.field` 或裸点路径；任一段缺失都返回 None，不抛错。"""
    path = expression[2:] if expression.startswith("$.") else expression
    current: Any = scope
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def expand(value: Any, scope: dict[str, Any]) -> Any:
    """整串等于表达式时替换为引用值；其余原样保留（不做字符串插值，避免注入歧义）。"""
    if isinstance(value, str):
        return resolve_path(scope, value) if value.startswith("$.") else value
    if isinstance(value, dict):
        return {key: expand(item, scope) for key, item in value.items()}
    if isinstance(value, list):
        return [expand(item, scope) for item in value]
    return value


def evaluate_condition(condition: dict[str, Any], scope: dict[str, Any]) -> bool:
    field = condition.get("field")
    operator = condition.get("op")
    if not isinstance(field, str) or operator not in ("nonempty", "empty", "contains", *COMPARISONS):
        return False
    actual = resolve_path(scope, field)
    if operator == "nonempty":
        return actual not in (None, "", [], {}, 0, False)
    if operator == "empty":
        return actual in (None, "", [], {})
    expected = condition.get("value")
    if operator == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        return isinstance(actual, list) and expected in actual
    try:
        return COMPARISONS[operator](actual, expected)
    except CoreError:
        return False


def evaluate_predicate(predicate: object, scope: dict[str, Any]) -> bool:
    if not isinstance(predicate, dict):
        return False
    if isinstance(predicate.get("all"), list):
        return all(evaluate_condition(item, scope) for item in predicate["all"])
    if isinstance(predicate.get("any"), list):
        return any(evaluate_condition(item, scope) for item in predicate["any"])
    return False


def node_scope(node: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    bounds = node.get("boundsPx") or {}
    width = int(bounds.get("right", 0)) - int(bounds.get("left", 0))
    height = int(bounds.get("bottom", 0)) - int(bounds.get("top", 0))
    return {"node": node, "width": width, "height": height, "window": snapshot.get("windowSizePx") or {}}


def contributions(registry: object, kind: str) -> list[tuple[str, dict[str, Any]]]:
    """读取所有 ready 插件的 Core 侧贡献；单个插件出错不影响其他插件。"""
    if registry is None:
        return []
    result: list[tuple[str, dict[str, Any]]] = []
    for entry in registry.index().get("items", []):
        if entry.get("status") != "ready":
            continue
        payload = registry.read_contribution(str(entry["id"]), kind)
        if isinstance(payload, dict):
            result.append((str(entry["id"]), payload))
    return result


def plugin_tools(registry: object) -> list[dict[str, Any]]:
    """插件工具在目录里以 plugin.{id}.{name} 暴露，与内置 12 项不共享命名空间。"""
    tools: list[dict[str, Any]] = []
    for plugin_id, payload in contributions(registry, "mcpTools"):
        for tool in payload.get("tools") or []:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                continue
            tools.append({
                "name": f"{PLUGIN_TOOL_PREFIX}{plugin_id}.{tool['name']}",
                "kind": "write" if tool.get("kind") == "write" else "read",
                "description": str(tool.get("description", ""))[:200],
                "inputSchema": tool.get("inputSchema") or {"type": "object"},
                "pluginId": plugin_id,
            })
    return tools


def find_declarative_tool(registry: object, qualified_name: str) -> tuple[str, dict[str, Any]]:
    """把 plugin.{id}.{name} 还原为 (pluginId, 工具声明)。"""
    remainder = qualified_name[len(PLUGIN_TOOL_PREFIX):]
    plugin_id, _, tool_name = remainder.partition(".")
    if not plugin_id or not tool_name:
        raise CoreError("INVALID_ARGUMENT", f"插件工具名不合法：{qualified_name}")
    payload = registry.read_contribution(plugin_id, "mcpTools") if registry is not None else None
    for tool in (payload or {}).get("tools") or []:
        if isinstance(tool, dict) and tool.get("name") == tool_name and isinstance(tool.get("steps"), list):
            if len(tool["steps"]) > MAX_STEPS:
                raise CoreError("PLUGIN_INVALID", f"插件工具步骤超过 {MAX_STEPS} 步。")
            return plugin_id, tool
    raise CoreError("PLUGIN_NOT_FOUND", f"插件未声明工具：{qualified_name}")
