"""插件清单契约的 Python 侧实现：常量、版本判定与归一化。

与 repos/contracts/schemas/plugin/manifest.json 对齐。归一化只做与运行环境无关的判定，
hosts 与 devicePlatforms 的过滤交给宿主前端（同一个 Core 同时服务壳与浏览器）。
"""

from __future__ import annotations

MANIFEST_SCHEMA_VERSION = "2.0"
LEGACY_MANIFEST_SCHEMA_VERSION = "1.0"

ASSET_SUFFIXES = frozenset({".html", ".js", ".mjs", ".css", ".json", ".png", ".svg", ".woff2"})
PERMISSIONS = ("snapshot.read", "device.read", "device.write", "mcp.call", "storage.local", "host.integration")
LEGACY_PERMISSION_MAP = {"device.read": "device.read", "device.write": "device.write", "snapshot.read": "snapshot.read"}
ACTIVATIONS = ("onOpen", "onSnapshot", "onCommand")
RUNTIMES = ("iframe", "declarative")
DEVICE_PLATFORMS = ("android", "ios", "harmony")
HOSTS = ("app", "web")
CARD_SLOTS = ("element.sidebar", "intelligence.bottom", "common.bottom")


def parse_version(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def satisfies(version: str, spec: object) -> bool:
    """极简 semver range：空格分隔的比较子句，全部满足才通过（例如 ">=0.1.0 <0.3.0"）。"""
    current = parse_version(version)
    if current is None:
        return False
    if not spec:
        return True
    if not isinstance(spec, str):
        return False
    for clause in spec.split():
        matched = False
        for prefix in (">=", "<=", "==", ">", "<"):
            if clause.startswith(prefix):
                target = parse_version(clause[len(prefix):])
                if target is None:
                    return False
                if prefix == ">=" and current < target:
                    return False
                if prefix == "<=" and current > target:
                    return False
                if prefix == "==" and current != target:
                    return False
                if prefix == ">" and current <= target:
                    return False
                if prefix == "<" and current >= target:
                    return False
                matched = True
                break
        if not matched and parse_version(clause) != current:
            return False
    return True


def clean_relative(value: object, *, suffix: str | None = None) -> str | None:
    """插件包内相对路径：拒绝绝对路径、父级穿越、反斜杠与隐藏段。"""
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("/") or value.startswith(".") or ".." in value or "\\" in value:
        return None
    if len(value) > 200:
        return None
    if suffix and not value.endswith(suffix):
        return None
    return value


def _string_list(value: object, allowed: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item in allowed]


def _tabs(raw: object) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for entry in raw[:4] if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        target = clean_relative(entry.get("entry"), suffix=".html")
        if not isinstance(entry.get("id"), str) or not isinstance(entry.get("title"), str) or not target:
            continue
        order = entry.get("order")
        items.append({
            "id": entry["id"],
            "title": entry["title"][:12],
            "icon": entry["icon"] if isinstance(entry.get("icon"), str) else None,
            "order": order if isinstance(order, int) and 100 <= order <= 999 else 500,
            "entry": target,
        })
    return items


def _cards(raw: object) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for entry in raw[:4] if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        target = clean_relative(entry.get("entry"), suffix=".html")
        if not isinstance(entry.get("id"), str) or entry.get("slot") not in CARD_SLOTS or not target:
            continue
        height = entry.get("height")
        items.append({
            "id": entry["id"],
            "slot": entry["slot"],
            "entry": target,
            "height": height if isinstance(height, int) and 80 <= height <= 480 else None,
        })
    return items


def normalize_contributions(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    result: dict[str, object] = {}
    tabs, cards = _tabs(raw.get("workbenchTabs")), _cards(raw.get("workbenchCards"))
    if tabs:
        result["workbenchTabs"] = tabs
    if cards:
        result["workbenchCards"] = cards
    commands = [
        {"id": entry["id"], "title": entry["title"][:24]}
        for entry in (raw.get("commands") or [])[:20]
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("title"), str)
    ] if isinstance(raw.get("commands"), list) else []
    if commands:
        result["commands"] = commands
    for key in ("mcpTools", "diagnosticRules"):
        block = raw.get(key)
        source = clean_relative(block.get("source"), suffix=".json") if isinstance(block, dict) else None
        if source:
            result[key] = {"source": source}
    return result or None
