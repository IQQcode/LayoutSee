"""IOSDeviceDriver：iOS 设备驱动，对上暴露与 AdbClient 同风格的接口。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
- 端口：真机 USB 47175-47179（usbmuxd 隧道）；模拟器 47164-47169（与主机共享 loopback，直连）
- 抓取流程：逐端口连接（失败继续下一端口）→ Ping(0.5s) → 版本校验 → app_info(0.5s)
  → 只接受 appIsInBackground=False 的前台 App（iOS 前台唯一，结果确定）
  → Hierarchy(202) 取整树 → 逐节点 AllAttrGroups(210) 拉属性组（上限 ATTR_NODES_LIMIT，
    对象不存在/注册表查询失败时静默空降级，快照仍可用）
  → 生成 uiautomator 风格 XML（bounds = frame × screenScale 四舍五入取整、负值截 0）
- XML 属性提取规则集中在 ATTR_EXTRACTION_RULES，真机校准时只改这一处
- 模拟器约束：LookinServer 单客户端——同一时刻 Lookin 官方客户端连着时端口不可达（枚举不到属正常）
"""
from __future__ import annotations

import socket
import time
import xml.etree.ElementTree as ET

from ..errors import CoreError
from .archiver import decode_rect
from .client import LookinClient
from ._utils import as_int
from .usbmux import UsbmuxClient

# XML 属性提取规则表：XML 属性名 → 匹配规则
# 精确 short-code 来自 LookinAttrIdentifiers.m（2026-10-26 依 LookinDemo 实弹校准）：
# - exact：attr.identifier 精确命中（首个命中生效）
# - classes：仅当节点类名（classChainList[0] 小写）命中其一才应用；缺省不限类
# - default：未命中时的缺省值
# 限制：LookinServer 属性组不含 accessibilityIdentifier/Label（resource-id/content-desc 留空，
# 侯选来源 ivarTraces 在静态树中为 null，后续经 FetchObject/TraceManager 路径补）
ATTR_EXTRACTION_RULES: dict[str, dict[str, object]] = {
    "text": {"exact": ("lb_t_t", "tf_t_t", "te_t_t"), "classes": ("uilabel", "uitextfield", "uitextview"), "default": ""},
    "enabled": {"exact": ("vl_i_i",), "default": True},  # userInteractionEnabled
    "clickable": {"exact": ("ct_e_e",), "default": False},  # UIControl enabled
    "scrollable": {"exact": (), "default": False},  # 由类名（UIScrollView 链）判定，见 _build_node
}

# 逐节点属性拉取上限：超过后其余节点无 text/resource-id（记 warning）
ATTR_NODES_LIMIT = 600
# 连续拿到空属性组的次数达到该值即早停（对象注册表失效时快速放弃，避免拖慢抓取）
ATTR_EMPTY_STREAK_LIMIT = 12


def round_px(value: float) -> int:
    """四舍五入取整（Python round 是银行家舍入，这里显式 half-up）。"""
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def flatten_app_info(info: dict[str, object]) -> dict[str, object]:
    """把 client.app_info 规整后的 App 信息抹平为诊断/快照共用的扁平 dict（缺失字段留空）。"""
    return {
        "appName": info.get("appName") or "",
        "appBundleIdentifier": info.get("appBundleIdentifier") or "",
        "deviceDescription": info.get("deviceDescription") or "",
        "osDescription": info.get("osDescription") or "",
        "deviceType": info.get("deviceType"),
        "screenWidth": _as_float(info.get("screenWidth")),
        "screenHeight": _as_float(info.get("screenHeight")),
        "screenScale": _as_float(info.get("screenScale")),
    }


def build_xml(
    display_items: object,
    scale: float,
    attr_groups_by_oid: dict[int, list[object]],
    warnings: list[str],
) -> str:
    """把 LookinDisplayItem 树渲染为 uiautomator 风格 XML。"""
    root = ET.Element("hierarchy", {"rotation": "0"})
    items = display_items if isinstance(display_items, list) else []
    if display_items is not None and not items:
        warnings.append("hierarchy 响应未提供 displayItems（键名需校准）。")
    for index, item in enumerate(items):
        _build_node(root, item, index, scale, attr_groups_by_oid, warnings)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


class IOSDeviceDriver:
    """iOS 设备驱动：devices() 枚举（真机 usbmux + 模拟器 loopback）、capture() 抓取。"""

    USB_PORTS = range(47175, 47180)
    SIM_PORTS = range(47164, 47170)
    SIMULATOR_SERIAL_PREFIX = "simulator:"
    SIM_CONNECT_TIMEOUT_S = 0.5

    def __init__(self, usbmux: UsbmuxClient | None = None, sim_ports: range | tuple[int, ...] | None = None) -> None:
        self.usbmux = usbmux or UsbmuxClient()
        self.sim_ports = tuple(sim_ports) if sim_ports is not None else tuple(self.SIM_PORTS)

    def available(self) -> bool:
        """usbmuxd 可用性（真机枚举前提）；模拟器枚举不依赖 usbmuxd。"""
        return self.usbmux.available()

    def devices(self) -> list[dict[str, object]]:
        now = int(time.time() * 1000)
        devices: list[dict[str, object]] = []
        if self.available():
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
        devices.extend(self._simulator_devices(now))
        return devices

    def _simulator_devices(self, now: int) -> list[dict[str, object]]:
        """扫本机 loopback 模拟器端口：连接+ping+app_info 全部通过且前台才算一台设备。

        连接被拒 = 该端口无 App 监听（未运行/未集成/Lookin 官方客户端占用中），静默跳过。
        """
        result: list[dict[str, object]] = []
        for port in self.sim_ports:
            stream = None
            try:
                stream = socket.create_connection(("127.0.0.1", port), timeout=self.SIM_CONNECT_TIMEOUT_S)
                client = LookinClient(stream)
                client.ping()
                info = client.app_info()
                if info.get("appIsInBackground") is not False:
                    continue
                app = flatten_app_info(info)
                result.append({
                    "deviceId": f"ios-sim-{port}",
                    "platform": "ios",
                    "serial": f"{self.SIMULATOR_SERIAL_PREFIX}{port}",
                    "model": str(app.get("appName") or ""),
                    "product": str(app.get("deviceDescription") or "Simulator"),
                    "status": "connected",
                    "capabilities": ["layout"],
                    "readonly": True,
                    "lastSeenAt": now,
                })
            except (CoreError, OSError):
                continue
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        return result

    def _open_stream(self, serial: str, port: int):
        """按设备类型建立到 LookinServer 的裸流：模拟器直连 loopback，真机走 usbmuxd 隧道。"""
        if serial.startswith(self.SIMULATOR_SERIAL_PREFIX):
            return socket.create_connection(("127.0.0.1", port), timeout=self.SIM_CONNECT_TIMEOUT_S)
        return self.usbmux.connect(serial, port)

    def is_simulator(self, serial: str) -> bool:
        return serial.startswith(self.SIMULATOR_SERIAL_PREFIX)

    def probe_port(
        self,
        serial: str,
        port: int,
        attempts: list[dict[str, object]],
    ) -> tuple[LookinClient, dict[str, object], int] | None:
        """探测单端口：连接 → Ping → app_info，只放行前台 App（appIsInBackground is False）。

        命中时返回 (client, info, port) 并保持连接（调用方负责关闭）；否则记录 attempts 后
        返回 None（连接已关闭）。解码 warnings 随 info/attempts 外送，不丢弃。
        供 capture 与诊断脚本复用。
        """
        stream = None
        keep = False
        try:
            stream = self._open_stream(serial, port)
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

    def capture(self, serial: str) -> dict[str, object]:
        """完整抓取：端口扫描选前台 App → 层级 + 属性 → uiautomator XML。

        serial 为真机 UDID 或 `simulator:{port}`；返回 {"xml", "window_size", "app", "warnings"}，
        无可用前台 App 抛 LOOKIN_APP_NOT_FOUND。
        """
        return self._capture(serial, include_raw=False)

    def capture_debug(self, serial: str) -> dict[str, object]:
        """诊断用抓取：在 capture() 基础上附 raw（解码后的层级树与属性详情），供真机校准键名。"""
        return self._capture(serial, include_raw=True)

    def _capture(self, serial: str, *, include_raw: bool) -> dict[str, object]:
        attempts: list[dict[str, object]] = []
        selected: tuple[LookinClient, dict[str, object], int] | None = None
        try:
            if self.is_simulator(serial):
                # 模拟器 serial 自带端口（simulator:47164），只探测该端口
                port = as_int(serial.split(":", 1)[1])
                if port is not None:
                    selected = self.probe_port(serial, port, attempts)
            else:
                for port in self.USB_PORTS:
                    selected = self.probe_port(serial, port, attempts)
                    if selected is not None:
                        break
            if selected is None:
                raise self._selection_error(serial, attempts)
            client, info, port = selected
            warnings: list[str] = []
            hierarchy = client.hierarchy()  # hierarchy 失败则整体失败
            display_items = hierarchy.get("displayItems") or []
            # App 信息优先用 Hierarchy 响应自带值，缺失回落探测阶段的 App 响应
            app_payload = hierarchy.get("appInfo") if isinstance(hierarchy.get("appInfo"), dict) and hierarchy.get("appInfo") else info
            app = flatten_app_info(app_payload)
            app["port"] = port
            scale = float(app.get("screenScale") or 1)
            attr_groups, attr_warnings = self._collect_attr_groups(client, display_items)
            warnings.extend(attr_warnings)
            warnings.extend(info.get("warnings") or [])
            warnings.extend(hierarchy.get("warnings") or [])
            xml = build_xml(display_items, scale, attr_groups, warnings)
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
                result["raw"] = {"displayItems": display_items, "appInfo": hierarchy.get("appInfo")}
            return result
        finally:
            if selected is not None:
                try:
                    selected[0].stream.close()
                except OSError:
                    pass

    def _collect_attr_groups(
        self,
        client: LookinClient,
        display_items: list[object],
    ) -> tuple[dict[int, list[object]], list[str]]:
        """逐节点 AllAttrGroups 收集属性组：{oid: [attrGroup...]}（view/layer 双写）。

        上限 ATTR_NODES_LIMIT；对象不存在（layer 未注册/已释放）是常态，静默空降级。
        已知限制：LookinServer 1.2.8 在 iOS 27 上 oid 注册表查询失败（官方 HierarchyDetails
        同样受影响），此时全部为空，快照仍可用（无 text/resource-id），详见 specs summary。
        """
        groups_by_oid: dict[int, list[object]] = {}
        warnings: list[str] = []
        fetched = 0
        empty = 0
        empty_streak = 0
        stack = list(display_items)
        while stack:
            item = stack.pop()
            if not isinstance(item, dict):
                continue
            subitems = item.get("subitems")
            if isinstance(subitems, list):
                stack.extend(subitems)
            layer = item.get("layerObject") if isinstance(item.get("layerObject"), dict) else {}
            view = item.get("viewObject") if isinstance(item.get("viewObject"), dict) else {}
            oid = as_int(layer.get("oid"))
            if oid is None:
                oid = as_int(view.get("oid"))
            if oid is None or oid in groups_by_oid:
                continue
            if fetched >= ATTR_NODES_LIMIT:
                warnings.append(f"属性节点数超过上限 {ATTR_NODES_LIMIT}，超出部分无 text/resource-id。")
                break
            try:
                result = client.all_attr_groups(oid)
            except CoreError as error:
                warnings.append(f"oid={oid} 属性拉取失败：{error.message}")
                continue
            fetched += 1
            groups = result.get("attrGroups") or []
            if groups:
                groups_by_oid[oid] = groups
                view_oid = as_int(view.get("oid"))
                if view_oid is not None and view_oid != oid:
                    groups_by_oid[view_oid] = groups
                empty_streak = 0
            else:
                empty += 1
                empty_streak += 1
                if empty_streak >= ATTR_EMPTY_STREAK_LIMIT:
                    warnings.append(f"连续 {empty_streak} 个节点无属性组，提前结束属性拉取。")
                    break
        if empty and not groups_by_oid and display_items:
            warnings.append(
                "属性数据不可用：LookinServer 的对象注册表查询失败（iOS 27 上官方客户端同样受影响），"
                "本次快照仅含层级与布局信息。"
            )
        return groups_by_oid, warnings

    def _selection_error(self, serial: str, attempts: list[dict[str, object]]) -> CoreError:
        codes = {str(item["code"]) for item in attempts if "code" in item}
        if codes == {"IOS_DEVICE_NOT_FOUND"}:
            return CoreError(
                "IOS_DEVICE_NOT_FOUND",
                f"usbmuxd 中未找到设备：{serial}。",
                details={"udid": serial, "attempts": attempts},
            )
        if codes == {"LOOKIN_VERSION_MISMATCH"}:
            return CoreError(
                "LOOKIN_VERSION_MISMATCH",
                "LookinServer 版本不兼容（需要 7，对应 LookinServer 1.2.8），请升级被测 App 后重试。",
                details={"udid": serial, "attempts": attempts},
            )
        if self.is_simulator(serial):
            # 模拟器失败绝大多数是连接拒绝（App 未运行 / 未集成 / Lookin 官方客户端占用），文案区分开
            return CoreError(
                "LOOKIN_APP_NOT_FOUND",
                "模拟器上未找到可连接的 Lookin App：请确认模拟器中的被测 App 正在前台运行（Debug 构建集成 LookinServer）"
                "；若正开着 Lookin 官方客户端，请先退出（LookinServer 同一时刻只允许一个客户端连接）。",
                retryable=True,
                details={"udid": serial, "attempts": attempts},
            )
        if codes == {"LOOKIN_UNAVAILABLE"}:
            return CoreError(
                "LOOKIN_UNAVAILABLE",
                "设备或 usbmuxd 通信失败，请确认 iOS 设备 USB 连接正常后重试。",
                retryable=True,
                details={"udid": serial, "attempts": attempts},
            )
        return CoreError(
            "LOOKIN_APP_NOT_FOUND",
            "未找到前台运行的 Lookin App：请确认被测 App 已集成 LookinServer（Debug 构建）并处于前台。",
            retryable=True,
            details={"udid": serial, "attempts": attempts},
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
    class_chain = _class_chain(item)
    for xml_attr, rule in ATTR_EXTRACTION_RULES.items():
        classes = rule.get("classes")
        if isinstance(classes, tuple) and class_name.lower() not in classes:
            attrs[xml_attr] = _format_value(rule.get("default"))
            continue
        value = _match_attr(flat_attrs, rule)
        attrs[xml_attr] = _format_value(rule.get("default") if value is None else value)
    # scrollable 由类链判定（UIScrollView 及子类）
    attrs["scrollable"] = "true" if any(name == "UIScrollView" for name in class_chain) else "false"
    element = ET.SubElement(parent, "node", attrs)
    subitems = item.get("subitems")
    if isinstance(subitems, list):
        for child_index, child in enumerate(subitems):
            _build_node(element, child, child_index, scale, attr_groups_by_oid, warnings)


def _node_class(item: dict[str, object]) -> str:
    chain = _class_chain(item)
    return chain[0] if chain else "UIView"


def _class_chain(item: dict[str, object]) -> list[str]:
    for key in ("viewObject", "layerObject"):
        obj = item.get(key)
        if isinstance(obj, dict):
            chain = obj.get("classChainList")
            if isinstance(chain, list) and chain and isinstance(chain[0], str) and chain[0]:
                return [str(name) for name in chain]
    return []


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
                    flat.extend(_attr_pairs(section.get("attributes") or section.get("attrs")))
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
    exact = rule.get("exact") or ()
    for identifier, value in flat_attrs:
        if identifier in exact:
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
