from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Any

from .adb import AdbClient
from .devices import DeviceGate, DeviceRegistry
from .errors import CoreError

MAX_NODES = 3000
MAX_DEPTH = 128
MAX_TEXT_LENGTH = 1024
KEEP_PER_DEVICE = 3
SNAPSHOT_TTL_S = 600

BOUNDS_PATTERN = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def parse_bounds(raw: str) -> tuple[int, int, int, int] | None:
    match = BOUNDS_PATTERN.search(raw or "")
    if not match:
        return None
    left, top, right, bottom = (int(match.group(index)) for index in range(1, 5))
    if right < left or bottom < top:
        return None
    return left, top, right, bottom


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text[:MAX_TEXT_LENGTH]


def normalize_nodes(xml_text: str, window_size: dict[str, int]) -> tuple[list[dict[str, object]], list[ET.Element], dict[int, str]]:
    """解析层级 XML 为 LayoutNode 列表；节点上限 3000、深度上限 128、文本限长。"""
    nodes: list[dict[str, object]] = []
    elements: list[ET.Element] = []
    element_to_key: dict[int, str] = {}
    width, height = window_size["width"], window_size["height"]
    if not xml_text:
        return nodes, elements, element_to_key

    if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
        return nodes, elements, element_to_key
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return nodes, elements, element_to_key

    def walk(element: ET.Element, parent_key: str | None, depth: int, parent_bounds: tuple[int, int, int, int] | None, child_index: int) -> None:
        if len(nodes) >= MAX_NODES or depth > MAX_DEPTH:
            return
        key = "0" if parent_key is None else f"{parent_key}.{child_index}"
        raw_attrs = dict(element.attrib)
        bounds = parse_bounds(raw_attrs.get("bounds", "")) or parent_bounds or (0, 0, 0, 0)
        has_bounds = parse_bounds(raw_attrs.get("bounds", "")) is not None
        left, top, right, bottom = bounds
        node: dict[str, object] = {
            "nodeKey": key,
            "parentKey": parent_key,
            "depth": depth,
            "childIndex": len(nodes),
            "className": str(raw_attrs.get("class") or element.tag),
            "resourceId": safe_text(raw_attrs.get("resource-id")),
            "text": safe_text(raw_attrs.get("text")),
            "contentDescription": safe_text(raw_attrs.get("content-desc")),
            "boundsPx": {"left": left, "top": top, "right": right, "bottom": bottom},
            "boundsNormalized": {
                "left": round(left / width, 6) if width else 0,
                "top": round(top / height, 6) if height else 0,
                "right": round(right / width, 6) if width else 0,
                "bottom": round(bottom / height, 6) if height else 0,
            },
            "visible": has_bounds and left < right and top < bottom,
            "enabled": raw_attrs.get("enabled", "true") == "true",
            "clickable": raw_attrs.get("clickable", "false") == "true",
            "scrollable": raw_attrs.get("scrollable", "false") == "true",
            "drawingOrder": len(nodes),
            "raw": raw_attrs,
        }
        nodes.append(node)
        elements.append(element)
        element_to_key[id(element)] = key
        for index, child in enumerate(element):
            if len(nodes) >= MAX_NODES or depth >= MAX_DEPTH:
                break
            walk(child, key, depth + 1, (left, top, right, bottom) if has_bounds else parent_bounds, index)

    if root.tag == "hierarchy" and len(root):
        for index, child in enumerate(root):
            walk(child, None, 0, None, index)
    else:
        walk(root, None, 0, None, 0)
    return nodes, elements, element_to_key

def png_size(png: bytes) -> tuple[int, int] | None:
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


class SnapshotStore:
    """快照缓存：每设备保留最近 3 份、10 分钟过期；ref 令牌不可跨启动复用。"""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, object]] = {}
        self._latest: dict[str, str] = {}
        self._by_device: dict[str, list[str]] = {}
        self._stale_tokens: set[str] = set()

    def put(self, record: dict[str, object]) -> dict[str, object]:
        snapshot_id = str(record["snapshot"]["snapshotId"])
        device_id = str(record["snapshot"]["deviceId"])
        with self._lock:
            self._records[snapshot_id] = record
            self._latest[device_id] = snapshot_id
            order = self._by_device.setdefault(device_id, [])
            order.append(snapshot_id)
            while len(order) > KEEP_PER_DEVICE:
                evicted = order.pop(0)
                if self._latest.get(device_id) == evicted:
                    continue
                self._evict(evicted)
            self._expire(device_id)
        return record

    def get(self, snapshot_id: str) -> dict[str, object]:
        with self._lock:
            record = self._records.get(snapshot_id)
            if record is None:
                raise CoreError("SNAPSHOT_STALE", "快照已过期，请重新抓取。", details={"snapshotId": snapshot_id})
            return record

    def latest_for(self, device_id: str) -> dict[str, object] | None:
        with self._lock:
            snapshot_id = self._latest.get(device_id)
            if snapshot_id is None:
                return None
            record = self._records.get(snapshot_id)
            if record is None:
                self._latest.pop(device_id, None)
                return None
            return record

    def resolve_ref(self, device_id: str, ref: str) -> tuple[dict[str, object], str]:
        """把 ref 解析为（快照记录, nodeKey）；旧快照 SNAPSHOT_STALE，非法 ref REF_NOT_FOUND。"""
        if not isinstance(ref, str) or not ref.startswith("r") or "_" not in ref:
            raise CoreError("REF_NOT_FOUND", "ref 不存在或格式非法，请重新查询元素。", details={"ref": ref})
        token, _, ordinal_text = ref[1:].partition("_")
        with self._lock:
            latest_id = self._latest.get(device_id)
            record = self._records.get(latest_id) if latest_id else None
            token_known = token in self._stale_tokens or any(item.get("ref_token") == token for item in self._records.values())
            if record is not None and record.get("ref_token") == token:
                target_ref = f"r{token}_{ordinal_text}"
                node_key = next((key for key, value in record.get("refs", {}).items() if value == target_ref), None)
                if node_key is None:
                    raise CoreError("REF_NOT_FOUND", "ref 不存在或格式非法，请重新查询元素。", details={"ref": ref})
                return record, str(node_key)
            if token_known:
                raise CoreError("SNAPSHOT_STALE", "ref 对应旧快照，请重新抓取后再操作。", details={"ref": ref})
            raise CoreError("REF_NOT_FOUND", "ref 不存在或格式非法，请重新查询元素。", details={"ref": ref})

    def ref_for(self, snapshot_id: str, node_key: str) -> str:
        with self._lock:
            record = self._records.get(snapshot_id)
            if record is None:
                raise CoreError("SNAPSHOT_STALE", "快照已过期，请重新抓取。")
            ref = record.get("refs", {}).get(node_key)
        if ref is None:
            raise CoreError("REF_NOT_FOUND", "ref 不存在或格式非法，请重新查询元素。", details={"nodeKey": node_key})
        return str(ref)

    def _evict(self, snapshot_id: str) -> None:
        record = self._records.pop(snapshot_id, None)
        if record:
            self._stale_tokens.add(str(record["ref_token"]))
            while len(self._stale_tokens) > 64:
                self._stale_tokens.pop()

    def _expire(self, device_id: str) -> None:
        now = time.time()
        order = self._by_device.get(device_id, [])
        for snapshot_id in list(order):
            record = self._records.get(snapshot_id)
            if record and now - int(record["snapshot"]["createdAt"]) / 1000 > SNAPSHOT_TTL_S and self._latest.get(device_id) != snapshot_id:
                order.remove(snapshot_id)
                self._evict(snapshot_id)


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result
    return result


class CaptureCoordinator:
    """原子抓取：冻结写队列 → dump → 截图 → 归一化 → 发布；幂等键复用结果。"""

    def __init__(self, adb: AdbClient, registry: DeviceRegistry, store: SnapshotStore, gate: DeviceGate) -> None:
        self.adb = adb
        self.registry = registry
        self.store = store
        self.gate = gate
        self._lock = threading.Lock()
        self._recent_keys: dict[str, tuple[str, str]] = {}

    def capture(self, device_id: str, idempotency_key: str | None = None) -> dict[str, object]:
        with self._lock:
            cached = self._recent_keys.get(device_id)
            if idempotency_key and cached and cached[0] == idempotency_key:
                try:
                    return self.store.get(cached[1])
                except CoreError:
                    pass
        with self.gate.acquire(device_id):
            record = self._capture(device_id)
            self.store.put(record)
            with self._lock:
                if idempotency_key:
                    self._recent_keys[device_id] = (idempotency_key, str(record["snapshot"]["snapshotId"]))
            return record

    def _context(self, serial: str) -> dict[str, object]:
        app = self.adb.current_app(serial)
        size = self.adb.window_size(serial)
        return {
            "foreground": app,
            "windowSizePx": size,
            "orientation": self.adb.orientation(serial),
        }

    def _capture(self, device_id: str) -> dict[str, object]:
        serial = self.registry.serial_for(device_id)
        before = self._context(serial)
        xml_text: str | None = None
        hierarchy_error: CoreError | None = None
        try:
            xml_text = self.adb.dump_xml(serial)
        except CoreError as error:
            hierarchy_error = error
        png: bytes | None = None
        screenshot_error: CoreError | None = None
        try:
            png = self.adb.screenshot(serial)
        except CoreError as error:
            screenshot_error = error
        after = self._context(serial)

        window_size = after["windowSizePx"]
        nodes, elements, element_to_key = normalize_nodes(xml_text or "", window_size)
        warnings: list[str] = []
        if hierarchy_error:
            warnings.append(f"层级抓取失败：{hierarchy_error.message}")
        if screenshot_error:
            warnings.append(f"截图失败：{screenshot_error.message}")
        if xml_text and not nodes:
            warnings.append("层级为空：可能是安全键盘、系统弹窗或无障碍树不可用。")

        synchronization = "best_effort" if before == after else "context_changed"
        if before != after:
            warnings.append("抓取期间页面上下文发生变化，结果与画面为尽力同步。")

        snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
        density = None
        try:
            density = self.adb.density(serial)
        except CoreError:
            pass

        screenshot_meta = None
        if png is not None:
            size = png_size(png)
            if size is not None:
                screenshot_meta = {
                    "width": size[0],
                    "height": size[1],
                    "contentUrl": f"/api/v1/snapshots/{snapshot_id}/screenshot",
                }

        ref_token = hmac.new(self.store._secret, snapshot_id.encode("utf-8"), hashlib.sha256).hexdigest()[:10]
        refs = {node["nodeKey"]: f"r{ref_token}_{_base36(index)}" for index, node in enumerate(nodes)}

        snapshot: dict[str, object] = {
            "snapshotId": snapshot_id,
            "deviceId": device_id,
            "createdAt": int(time.time() * 1000),
            "foreground": before["foreground"],
            "windowSizePx": window_size,
            "density": density,
            "hierarchyAccuracy": "best_effort" if nodes else "limited",
            "synchronization": synchronization,
            "screenshot": screenshot_meta,
            "roots": [nodes[0]["nodeKey"]] if nodes else [],
            "nodes": nodes,
            "warnings": warnings,
        }
        return {
            "snapshot": snapshot,
            "png": png,
            "xml": xml_text or "",
            "elements": elements,
            "element_to_key": element_to_key,
            "refs": refs,
            "ref_token": ref_token,
        }
