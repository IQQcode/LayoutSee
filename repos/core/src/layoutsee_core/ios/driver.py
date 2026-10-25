"""IOSDeviceDriver：iOS 设备驱动，对上暴露与 AdbClient 同风格的接口。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
- 端口：真机 USB 47175-47179（LookinServer 默认监听；模拟器 47164-47169 本版不做）
- 抓取流程：逐端口 usbmux Connect（失败继续下一端口）→ Ping(0.5s) → 版本校验 → app_info(0.5s)
  → 只接受 appIsInBackground=False 的前台 App（iOS 前台唯一，结果确定）
  → hierarchy(5s) + hierarchy_details(5s，失败降级：树照出、attrGroups 空、warnings 注明)
  → 生成 uiautomator 风格 XML（bounds = frame × screenScale 四舍五入取整、负值截 0）
- XML 属性提取规则集中在 ATTR_EXTRACTION_RULES，真机校准时只改这一处
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

from ..errors import CoreError
from .archiver import decode_rect
from .client import LookinClient
from ._utils import as_int
from .usbmux import UsbmuxClient

# XML 属性提取规则表：XML 属性名 → 匹配规则（真机校准时只改这里）
# - all：attr.identifier 需同时包含的全部关键词（小写宽松匹配）
# - any：attr.identifier 命中任一关键词即可（attr 顺序即优先级，首个命中者生效）
# - classes：仅当节点类名（classChainList[0] 小写）命中其一才应用；缺省不限类
# - default：未命中时的缺省值（布尔输出 "true"/"false"，文本缺省空串）
ATTR_EXTRACTION_RULES: dict[str, dict[str, object]] = {
    "text": {"all": ("text",), "classes": ("uilabel", "uitextview", "uitextfield"), "default": ""},
    # accessibilityIdentifier 命中 "identifier"；避免用 "accessibility" 兜底（会误匹配 Label）
    "resource-id": {"any": ("identifier",), "default": ""},
    "content-desc": {"all": ("accessibility", "label"), "default": ""},
    "enabled": {"any": ("enabled",), "default": True},
    "clickable": {"any": ("click",), "default": False},
    "scrollable": {"any": ("scroll",), "default": False},
}


def round_px(value: float) -> int:
    """四舍五入取整（Python round 是银行家舍入，这里显式 half-up）。"""
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def flatten_app_info(info: dict[str, object]) -> dict[str, object]:
    """把 App 响应抹平为诊断/快照共用的扁平 dict（缺失字段留空）。"""
    data = info.get("data") if isinstance(info.get("data"), dict) else {}
    return {
        "appName": data.get("appName") or "",
        "appBundleIdentifier": data.get("appBundleIdentifier") or "",
        "deviceDescription": data.get("deviceDescription") or "",
        "osDescription": data.get("osDescription") or "",
        "deviceType": data.get("deviceType"),
        "screenWidth": _as_float(data.get("screenWidth")),
        "screenHeight": _as_float(data.get("screenHeight")),
        "screenScale": _as_float(data.get("screenScale")),
    }


def build_xml(
    data: object,
    scale: float,
    attr_groups_by_oid: dict[int, list[object]],
    warnings: list[str],
) -> str:
    """把解码后的 Lookin 层级树渲染为 uiautomator 风格 XML。"""
    root = ET.Element("hierarchy", {"rotation": "0"})
    display_items: list[object] = []
    if isinstance(data, dict) and isinstance(data.get("displayItems"), list):
        display_items = data["displayItems"]
    elif data is not None:
        # data 非 None 却没有 displayItems：真实键名待真机校准，记 warning 不报错
        warnings.append(f"hierarchy 响应缺少 displayItems（键名需真机校准）：{type(data).__name__}")
    for index, item in enumerate(display_items):
        _build_node(root, item, index, scale, attr_groups_by_oid, warnings)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


class IOSDeviceDriver:
    """iOS 设备驱动：devices() 枚举、capture() 抓取（Task 2 接入 registry/capture）。"""

    USB_PORTS = range(47175, 47180)

    def __init__(self, usbmux: UsbmuxClient | None = None) -> None:
        self.usbmux = usbmux or UsbmuxClient()

    def available(self) -> bool:
        return self.usbmux.available()

    def devices(self) -> list[dict[str, object]]:
        if not self.available():
            return []
        now = int(time.time() * 1000)
        devices: list[dict[str, object]] = []
        for entry in self.usbmux.list_devices():
            udid = str(entry["udid"])
            properties = entry.get("properties") if isinstance(entry.get("properties"), dict) else {}
            devices.append({
                "deviceId": f"ios-{udid}",
                "platform": "ios",
                "serial": udid,
                "model": "",
                "product": str(properties.get("ProductType") or ""),
                "status": "connected",
                "capabilities": ["layout"],
                "readonly": True,
                "lastSeenAt": now,
            })
        return devices

    def probe_port(
        self,
        udid: str,
        port: int,
        attempts: list[dict[str, object]],
    ) -> tuple[LookinClient, dict[str, object], int] | None:
        """探测单端口：Connect → Ping → app_info，只放行前台 App（appIsInBackground is False）。

        命中时返回 (client, info, port) 并保持连接（调用方负责关闭）；否则记录 attempts 后
        返回 None（连接已关闭）。解码 warnings 随 info/attempts 外送，不丢弃。
        供 capture 与诊断脚本复用。
        """
        stream = None
        keep = False
        try:
            stream = self.usbmux.connect(udid, port)
            client = LookinClient(stream)
            ping_warnings: list[str] = []
            client.ping(ping_warnings)
            info = client.app_info()
            decode_warnings = ping_warnings + list(info.get("warnings") or [])
            if info.get("appIsInBackground") is not False:
                attempts.append({
                    "port": port,
                    "stage": "filter",
                    "appIsInBackground": info.get("appIsInBackground"),
                    "warnings": decode_warnings,
                })
                return None
            info["warnings"] = decode_warnings  # ping + app 解码警告随 info 交给调用方
            keep = True
            return client, info, port
        except CoreError as error:
            attempts.append({"port": port, "code": error.code, "message": error.message})
            return None
        except OSError as error:  # peertalk 收发阶段的裸 socket 错误，统一归类
            wrapped = CoreError(
                "LOOKIN_UNAVAILABLE",
                f"与设备端口 {port} 通信失败：{error}",
                details={"port": port, "reason": str(error)},
            )
            attempts.append({"port": port, "code": wrapped.code, "message": wrapped.message})
            return None
        finally:
            if stream is not None and not keep:
                try:
                    stream.close()
                except OSError:
                    pass

    def capture(self, udid: str) -> dict[str, object]:
        """完整抓取：端口扫描选前台 App → 层级 + 属性 → uiautomator XML。

        返回 {"xml", "window_size", "app", "warnings"}；无可用前台 App 抛 LOOKIN_APP_NOT_FOUND。
        """
        return self._capture(udid, include_raw=False)

    def capture_debug(self, udid: str) -> dict[str, object]:
        """诊断用抓取：在 capture() 基础上附 raw（解码后的层级树与属性详情），供真机校准键名。"""
        return self._capture(udid, include_raw=True)

    def _capture(self, udid: str, *, include_raw: bool) -> dict[str, object]:
        attempts: list[dict[str, object]] = []
        selected: tuple[LookinClient, dict[str, object], int] | None = None
        try:
            for port in self.USB_PORTS:
                selected = self.probe_port(udid, port, attempts)
                if selected is not None:
                    break
            if selected is None:
                raise self._selection_error(udid, attempts)
            client, info, port = selected
            warnings: list[str] = []
            hierarchy = client.hierarchy()  # hierarchy 失败则整体失败
            details: dict[str, object] = {"attrGroupsByOid": {}, "batches": [], "droppedImageFieldCount": 0, "warnings": []}
            try:
                details = client.hierarchy_details()
            except CoreError as error:
                warnings.append(f"属性拉取失败，已降级为无属性树：{error.message}")
            warnings.extend(info.get("warnings") or [])
            warnings.extend(hierarchy.get("warnings") or [])
            warnings.extend(details.get("warnings") or [])
            app = flatten_app_info(info)
            app["port"] = port
            scale = float(app.get("screenScale") or 1)
            attr_groups = details.get("attrGroupsByOid") if isinstance(details.get("attrGroupsByOid"), dict) else {}
            xml = build_xml(hierarchy.get("data"), scale, attr_groups, warnings)
            result: dict[str, object] = {
                "xml": xml,
                "window_size": {
                    "width": round_px(float(app.get("screenWidth") or 0) * scale),
                    "height": round_px(float(app.get("screenHeight") or 0) * scale),
                },
                "app": app,
                "warnings": warnings,
            }
            if include_raw:
                result["raw"] = {"hierarchy": hierarchy.get("data"), "details": details}
            return result
        finally:
            if selected is not None:
                try:
                    selected[0].stream.close()
                except OSError:
                    pass

    @staticmethod
    def _selection_error(udid: str, attempts: list[dict[str, object]]) -> CoreError:
        codes = {str(item["code"]) for item in attempts if "code" in item}
        if codes == {"IOS_DEVICE_NOT_FOUND"}:
            return CoreError(
                "IOS_DEVICE_NOT_FOUND",
                f"usbmuxd 中未找到设备：{udid}。",
                details={"udid": udid, "attempts": attempts},
            )
        if codes == {"LOOKIN_VERSION_MISMATCH"}:
            return CoreError(
                "LOOKIN_VERSION_MISMATCH",
                "LookinServer 版本不兼容（需要 7，对应 LookinServer 1.2.8），请升级被测 App 后重试。",
                details={"udid": udid, "attempts": attempts},
            )
        if codes == {"LOOKIN_UNAVAILABLE"}:
            return CoreError(
                "LOOKIN_UNAVAILABLE",
                "设备或 usbmuxd 通信失败，请确认 iOS 设备 USB 连接正常后重试。",
                retryable=True,
                details={"udid": udid, "attempts": attempts},
            )
        return CoreError(
            "LOOKIN_APP_NOT_FOUND",
            "未找到前台运行的 Lookin App：请确认被测 App 已集成 LookinServer（Debug 构建）并处于前台。",
            retryable=True,
            details={"udid": udid, "attempts": attempts},
        )


def _build_node(
    parent: ET.Element,
    item: object,
    index: int,
    scale: float,
    attr_groups_by_oid: dict[int, list[object]],
    warnings: list[str],
) -> None:
    if not isinstance(item, dict):
        return
    class_name = _node_class(item)
    attrs: dict[str, str] = {"index": str(index), "class": class_name}
    frame = decode_rect(item.get("frame"))
    if frame is None:
        if item.get("frame") is not None:
            warnings.append(f"frame 无法解析（真机校准点）：class={class_name}")
        attrs["bounds"] = "[0,0][0,0]"
    else:
        left = max(0, round_px(frame["x"] * scale))
        top = max(0, round_px(frame["y"] * scale))
        right = max(0, round_px((frame["x"] + frame["width"]) * scale))
        bottom = max(0, round_px((frame["y"] + frame["height"]) * scale))
        attrs["bounds"] = f"[{left},{top}][{right},{bottom}]"
    flat_attrs = _flat_attrs(item, attr_groups_by_oid)
    for xml_attr, rule in ATTR_EXTRACTION_RULES.items():
        classes = rule.get("classes")
        if isinstance(classes, tuple) and class_name.lower() not in classes:
            attrs[xml_attr] = _format_value(rule.get("default"))
            continue
        value = _match_attr(flat_attrs, rule)
        attrs[xml_attr] = _format_value(rule.get("default") if value is None else value)
    element = ET.SubElement(parent, "node", attrs)
    subitems = item.get("subitems")
    if isinstance(subitems, list):
        for child_index, child in enumerate(subitems):
            _build_node(element, child, child_index, scale, attr_groups_by_oid, warnings)


def _node_class(item: dict[str, object]) -> str:
    for key in ("viewObject", "layerObject"):
        obj = item.get(key)
        if isinstance(obj, dict):
            chain = obj.get("classChainList")
            if isinstance(chain, list) and chain and isinstance(chain[0], str) and chain[0]:
                return chain[0]
    return "UIView"


def _flat_attrs(item: dict[str, object], attr_groups_by_oid: dict[int, list[object]]) -> list[tuple[str, object]]:
    groups: list[object] = []
    own = item.get("attributesGroupList")
    if isinstance(own, list):
        groups.extend(own)
    for key in ("viewObject", "layerObject"):
        obj = item.get(key)
        if isinstance(obj, dict):
            oid = as_int(obj.get("oid"))
            if oid is not None:
                groups.extend(attr_groups_by_oid.get(oid) or [])
    flat: list[tuple[str, object]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        sections = group.get("attrSections")
        if isinstance(sections, list):
            for section in sections:
                if isinstance(section, dict):
                    flat.extend(_attr_pairs(section.get("attrs")))
        flat.extend(_attr_pairs(group.get("attrs")))  # 宽松：组上直接挂 attrs 的形态
    return flat


def _attr_pairs(attrs: object) -> list[tuple[str, object]]:
    pairs: list[tuple[str, object]] = []
    if isinstance(attrs, list):
        for attr in attrs:
            if isinstance(attr, dict):
                pairs.append((str(attr.get("identifier") or ""), attr.get("value")))
    return pairs


def _match_attr(flat_attrs: list[tuple[str, object]], rule: dict[str, object]) -> object | None:
    all_keywords = rule.get("all") or ()
    any_keywords = rule.get("any") or ()
    for identifier, value in flat_attrs:
        lowered = identifier.lower()
        if all_keywords and not all(keyword in lowered for keyword in all_keywords):
            continue
        if any_keywords and not any(keyword in lowered for keyword in any_keywords):
            continue
        return value
    return None


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
