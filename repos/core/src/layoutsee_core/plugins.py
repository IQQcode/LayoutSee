"""插件索引层：懒扫盘、签名缓存与资源路径解析。

冷启动约定：构造函数不触盘，首次 index() 才解析；签名为 (相对路径, mtime_ns, size)，
命中时只 stat 不解析，因此插件数量不影响 Core 启动耗时。
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .errors import CoreError
from .plugin_manifest import (
    ACTIVATIONS,
    ASSET_SUFFIXES,
    DEVICE_PLATFORMS,
    HOSTS,
    LEGACY_MANIFEST_SCHEMA_VERSION,
    LEGACY_PERMISSION_MAP,
    MANIFEST_SCHEMA_VERSION,
    PERMISSIONS,
    RUNTIMES,
    clean_relative,
    normalize_contributions,
    parse_version,
    satisfies,
)

INDEX_SCHEMA_VERSION = "1.0"
INDEX_CACHE_NAME = ".index.json"
MAX_MANIFEST_BYTES = 65_536


def _error(code: str, message: str) -> dict[str, object]:
    return {"code": code, "message": message, "retryable": False}


def _upgrade_legacy(raw: dict[str, object]) -> dict[str, object]:
    """v1 清单兼容读取：entry 变成单个 Tab，platforms 只取设备平台，网络权限直接丢弃。"""
    platforms = [item for item in (raw.get("platforms") or []) if item in DEVICE_PLATFORMS] or list(DEVICE_PLATFORMS[:1])
    name = raw["name"] if isinstance(raw.get("name"), str) else str(raw.get("id", ""))
    return {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "id": raw.get("id"),
        "name": name,
        "version": raw.get("version"),
        "hosts": list(HOSTS),
        "devicePlatforms": platforms,
        "activation": "onOpen",
        "runtime": "iframe",
        "permissions": [LEGACY_PERMISSION_MAP[item] for item in (raw.get("permissions") or []) if item in LEGACY_PERMISSION_MAP],
        "contributions": {"workbenchTabs": [{"id": "main", "title": name, "entry": raw.get("entry")}]},
    }


def normalize_manifest(raw: object, product_version: str) -> dict[str, object]:
    """把清单归一化为索引条目；只做与运行环境无关的判定。"""
    if not isinstance(raw, dict):
        return {"status": "invalid", "error": _error("PLUGIN_INVALID", "manifest.json 不是 JSON 对象")}
    legacy = raw.get("schemaVersion") == LEGACY_MANIFEST_SCHEMA_VERSION
    if legacy:
        raw = _upgrade_legacy(raw)
    if raw.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        return {"status": "invalid", "error": _error("PLUGIN_INVALID", "不支持的清单版本")}
    plugin_id, name = raw.get("id"), raw.get("name")
    if not isinstance(plugin_id, str) or not plugin_id or len(plugin_id) > 64:
        return {"status": "invalid", "error": _error("PLUGIN_INVALID", "清单缺少合法 id")}
    if not isinstance(name, str) or not name:
        return {"status": "invalid", "error": _error("PLUGIN_INVALID", "清单缺少 name")}
    if parse_version(raw.get("version")) is None:
        return {"id": plugin_id, "status": "invalid", "error": _error("PLUGIN_INVALID", "version 必须是 x.y.z")}
    contributions = normalize_contributions(raw.get("contributions"))
    if contributions is None:
        return {"id": plugin_id, "status": "invalid", "error": _error("PLUGIN_INVALID", "清单缺少可用的 contributions")}
    activation = raw.get("activation") if raw.get("activation") in ACTIVATIONS else ACTIVATIONS[0]
    entry: dict[str, object] = {
        "id": plugin_id,
        "name": name[:80],
        "version": raw["version"],
        "description": str(raw.get("description") or "")[:200],
        "hosts": [item for item in (raw.get("hosts") or HOSTS) if item in HOSTS] or list(HOSTS),
        "devicePlatforms": [item for item in (raw.get("devicePlatforms") or []) if item in DEVICE_PLATFORMS] or list(DEVICE_PLATFORMS[:1]),
        "activation": activation,
        "runtime": raw.get("runtime") if raw.get("runtime") in RUNTIMES else RUNTIMES[0],
        "permissions": [item for item in (raw.get("permissions") or []) if item in PERMISSIONS],
        "contributions": contributions,
        "status": "ready",
    }
    if legacy:
        entry["legacy"] = True
    spec = raw["engines"].get("layoutsee") if isinstance(raw.get("engines"), dict) else None
    if spec and not satisfies(product_version, spec):
        entry["status"] = "incompatible"
        entry["error"] = _error("PLUGIN_INCOMPATIBLE", f"插件要求 LayoutSee {spec}，当前 {product_version}")
    return entry


class PluginRegistry:
    def __init__(self, plugins_dir: Path, builtin_dir: Path | None = None, product_version: str = "22.6.1") -> None:
        self.plugins_dir = Path(plugins_dir)
        self.builtin_dir = Path(builtin_dir) if builtin_dir else None
        self.product_version = product_version
        self._lock = threading.RLock()
        self._items: list[dict[str, object]] | None = None
        self._roots: dict[str, Path] = {}
        self._signature: list[list[object]] | None = None
        self.parse_count = 0

    def _sources(self) -> list[tuple[str, Path]]:
        sources: list[tuple[str, Path]] = []
        if self.builtin_dir:
            sources.append(("builtin", self.builtin_dir))
        sources.append(("local", self.plugins_dir))
        return sources

    def _signature_now(self) -> list[list[object]]:
        signature: list[list[object]] = []
        for origin, directory in self._sources():
            if not directory.is_dir():
                continue
            for child in sorted(directory.iterdir()):
                manifest = child / "manifest.json"
                try:
                    info = manifest.stat()
                except OSError:
                    continue
                signature.append([origin, child.name, info.st_mtime_ns, info.st_size])
        return signature

    def _scan(self) -> tuple[list[dict[str, object]], dict[str, Path]]:
        items: dict[str, dict[str, object]] = {}
        roots: dict[str, Path] = {}
        for origin, directory in self._sources():
            if not directory.is_dir():
                continue
            for child in sorted(directory.iterdir()):
                manifest = child / "manifest.json"
                if not manifest.is_file():
                    continue
                self.parse_count += 1
                try:
                    if manifest.stat().st_size > MAX_MANIFEST_BYTES:
                        raise ValueError("manifest too large")
                    entry = normalize_manifest(json.loads(manifest.read_text(encoding="utf-8")), self.product_version)
                except (OSError, ValueError):
                    entry = {"status": "invalid", "error": _error("PLUGIN_INVALID", "manifest.json 无法解析")}
                entry.setdefault("id", child.name)
                entry["origin"] = origin
                plugin_id = str(entry["id"])
                if plugin_id in items and items[plugin_id].get("origin") == "builtin":
                    entry["overrides"] = "builtin"
                items[plugin_id] = entry
                if entry.get("status") != "invalid":
                    roots[plugin_id] = child
        return list(items.values()), roots

    def index(self, *, refresh: bool = False) -> dict[str, object]:
        with self._lock:
            signature = self._signature_now()
            if not refresh and self._items is not None and signature == self._signature:
                return self._payload(cache_hit=True)
            if not refresh and self._items is None:
                cached = self._read_disk_cache(signature)
                if cached is not None:
                    self._items, self._signature = cached, signature
                    self._roots = self._roots_from(cached)
                    return self._payload(cache_hit=True)
            self._items, self._roots = self._scan()
            self._signature = signature
            self._write_disk_cache(signature)
            return self._payload(cache_hit=False)

    def _roots_from(self, items: list[dict[str, object]]) -> dict[str, Path]:
        roots: dict[str, Path] = {}
        for entry in items:
            directory = entry.get("_dir")
            if isinstance(directory, str) and entry.get("status") != "invalid":
                roots[str(entry.get("id"))] = Path(directory)
        return roots

    def _payload(self, *, cache_hit: bool) -> dict[str, object]:
        items = [{key: value for key, value in entry.items() if not key.startswith("_")} for entry in self._items or []]
        payload: dict[str, object] = {
            "schemaVersion": INDEX_SCHEMA_VERSION,
            "directory": str(self.plugins_dir),
            "generatedAt": int(time.time() * 1000),
            "cacheHit": cache_hit,
            "items": items,
        }
        if self.builtin_dir:
            payload["builtinDirectory"] = str(self.builtin_dir)
        return payload

    def _cache_path(self) -> Path:
        return self.plugins_dir / INDEX_CACHE_NAME

    def _read_disk_cache(self, signature: list[list[object]]) -> list[dict[str, object]] | None:
        try:
            raw = json.loads(self._cache_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict) or raw.get("signature") != signature:
            return None
        items = raw.get("items")
        return items if isinstance(items, list) else None

    def _write_disk_cache(self, signature: list[list[object]]) -> None:
        items = []
        for entry in self._items or []:
            copy = dict(entry)
            root = self._roots.get(str(entry.get("id")))
            if root is not None:
                copy["_dir"] = str(root)
            items.append(copy)
        payload = {"signature": signature, "items": items}
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._cache_path().with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._cache_path())
        except OSError:
            pass

    def entry(self, plugin_id: str) -> dict[str, object]:
        self.index()
        with self._lock:
            for item in self._items or []:
                if item.get("id") == plugin_id:
                    return {key: value for key, value in item.items() if not key.startswith("_")}
        raise CoreError("PLUGIN_NOT_FOUND", f"未找到插件：{plugin_id}")

    def resolve_asset(self, plugin_id: str, relative: object) -> Path:
        """解析插件包内资源；逃逸、符号链接与非白名单后缀一律拒绝。"""
        self.index()
        root = self._roots.get(plugin_id)
        if root is None:
            raise CoreError("PLUGIN_NOT_FOUND", f"未找到插件：{plugin_id}")
        cleaned = clean_relative(relative)
        if cleaned is None:
            raise CoreError("PERMISSION_REQUIRED", "插件资源路径非法。", details={"pluginId": plugin_id})
        candidate = root / cleaned
        probe = root
        for part in cleaned.split("/"):
            probe = probe / part
            if probe.is_symlink():
                raise CoreError("PERMISSION_REQUIRED", "插件资源禁止符号链接。", details={"pluginId": plugin_id})
        resolved = candidate.resolve()
        if not str(resolved).startswith(str(root.resolve()) + os.sep):
            raise CoreError("PERMISSION_REQUIRED", "插件资源越界访问已被拒绝。", details={"pluginId": plugin_id})
        if resolved.suffix not in ASSET_SUFFIXES or not resolved.is_file():
            raise CoreError("PLUGIN_NOT_FOUND", "插件资源不存在。", details={"pluginId": plugin_id})
        return resolved

    def read_contribution(self, plugin_id: str, kind: str) -> dict[str, object] | None:
        """读取 mcpTools / diagnosticRules 声明文件；非法或缺失返回 None。"""
        entry = self.entry(plugin_id)
        if entry.get("status") != "ready":
            return None
        block = (entry.get("contributions") or {}).get(kind) if isinstance(entry.get("contributions"), dict) else None
        source = block.get("source") if isinstance(block, dict) else None
        if not source:
            return None
        try:
            payload = json.loads(self.resolve_asset(plugin_id, source).read_text(encoding="utf-8"))
        except (CoreError, OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None
