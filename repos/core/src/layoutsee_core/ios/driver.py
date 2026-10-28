"""IOSDeviceDriver：iOS 设备驱动，对上暴露与 AdbClient 同风格的接口。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
- 端口：真机 USB 47175-47179（usbmuxd 隧道）；模拟器 47164-47169（与主机共享 loopback，直连）
- 抓取流程：逐端口连接（失败继续下一端口）→ Ping(0.5s) → 版本校验 → app_info(0.5s)
  → 只接受 appIsInBackground=False 的前台 App（iOS 前台唯一，结果确定）
  → Hierarchy(202) 取整树 → 逐节点 AllAttrGroups(210) 拉属性组（上限 ATTR_NODES_LIMIT，
    对象已释放等空属性静默降级，快照仍可用）
  → 生成 uiautomator 风格 XML（bounds = 父链累加后的窗口绝对坐标 × screenScale 取整、负值截 0）
    并产出逐节点 extras（属性分组 + ivar 名），nodeKey 与 normalize_nodes 键位对齐
- XML 属性提取规则集中在 ATTR_EXTRACTION_RULES，真机校准时只改这一处
- 模拟器约束：LookinServer 单客户端——同一时刻 Lookin 官方客户端连着时端口不可达（枚举不到属正常）
"""
from __future__ import annotations

import socket
import time
import xml.etree.ElementTree as ET

from ..errors import CoreError
from .archiver import decode_rect
from .attrs import best_ivar, build_extras
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


# 模拟器 serial 前缀（simulator:{port}）；模块级导出供快照层判断设备类型
IOS_SIMULATOR_PREFIX = "simulator:"


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
) -> tuple[str, dict[str, dict[str, object]]]:
    """把 LookinDisplayItem 树渲染为 uiautomator 风格 XML，并产出逐节点 extras。

    返回 (xml, extras_by_node_key)。bounds 为**窗口绝对坐标**：LookinServer 下发的
    item.frame 是相对父视图的坐标（LKS_HierarchyDisplayItemsMaker 直接取 layer.frame，
    官方客户端自行累加 frameToRoot），这里按官方 calculateFrameToRoot 公式沿父链累加
    （frame.origin - 父级 bounds.origin + 父级 frameToRoot）后再乘 scale。
    nodeKey 键位与 normalize_nodes 一致（根 = str(索引)，子 = 父键 + "." + 子索引），
    快照层按键回填 node.extras。
    """
    root = ET.Element("hierarchy", {"rotation": "0"})
    items = display_items if isinstance(display_items, list) else []
    if display_items is not None and not items:
        warnings.append("hierarchy 响应未提供 displayItems（键名需校准）。")
    extras_by_key: dict[str, dict[str, object]] = {}
    for index, item in enumerate(items):
        _build_node(root, item, str(index), (0.0, 0.0), (0.0, 0.0), scale, attr_groups_by_oid, warnings, extras_by_key)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    return xml, extras_by_key


class IOSDeviceDriver:
    """iOS 设备驱动：devices() 枚举（真机 usbmux + 模拟器 loopback）、capture() 抓取。"""

    USB_PORTS = range(47175, 47180)
    SIM_PORTS = range(47164, 47170)
    SIMULATOR_SERIAL_PREFIX = IOS_SIMULATOR_PREFIX
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

        serial 为真机 UDID 或 `simulator:{port}`；返回 {"xml", "extras", "window_size", "app", "warnings"}，
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
            # key window 的 group 渲染图 = 全 App 真实内容（drawViewHierarchyInRect 原生分辨率），
            # 模拟器/真机通用且与层级同步，作为画布底图（模拟器下 simctl 仅作回退）
            screenshot = self._fetch_window_screenshot(client, display_items, warnings)
            attr_groups, attr_warnings = self._collect_attr_groups(client, display_items)
            warnings.extend(attr_warnings)
            warnings.extend(info.get("warnings") or [])
            warnings.extend(hierarchy.get("warnings") or [])
            xml, extras_by_key = build_xml(display_items, scale, attr_groups, warnings)
            result: dict[str, object] = {
                "xml": xml,
                "extras": extras_by_key,
                "screenshot": screenshot,
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

    def _fetch_window_screenshot(
        self,
        client: LookinClient,
        display_items: list[object],
        warnings: list[str],
    ) -> bytes | None:
        """203 拉 key window 的 group 渲染图（真实内容底图）；失败静默降级返回 None。"""
        if not isinstance(display_items, list) or not display_items:
            return None
        key_window = next(
            (item for item in display_items if isinstance(item, dict) and item.get("representedAsKeyWindow") is True),
            display_items[0],
        )
        layer = key_window.get("layerObject") if isinstance(key_window.get("layerObject"), dict) else {}
        window_oid = as_int(layer.get("oid"))
        if window_oid is None:
            return None
        screenshot = client.fetch_display_item_screenshot(window_oid)
        if screenshot is None:
            warnings.append("窗口渲染图（203）拉取失败，底图可能缺失。")
        return screenshot

    def _collect_attr_groups(
        self,
        client: LookinClient,
        display_items: list[object],
    ) -> tuple[dict[int, list[object]], list[str]]:
        """逐节点 AllAttrGroups 收集属性组：{oid: [attrGroup...]}（view/layer 双写）。

        上限 ATTR_NODES_LIMIT；210 只认 layer 的 oid（handler 校验 CALayer），view 的
        oid 查表返回 ObjNotFound 属常态，静默空降级。
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
                "属性数据不可用：逐节点属性拉取均未命中（对象可能已释放或 LookinServer 未注册），"
                "本次快照仅含层级与布局信息，请保持被测 App 前台后重试。"
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
    key: str,
    origin: tuple[float, float],
    parent_bounds_origin: tuple[float, float],
    scale: float,
    attr_groups_by_oid: dict[int, list[object]],
    warnings: list[str],
    extras_by_key: dict[str, dict[str, object]],
) -> None:
    if not isinstance(item, dict):
        return
    class_name = _node_class(item)
    attrs: dict[str, str] = {"index": str(key.rsplit(".", 1)[-1]), "class": class_name}
    frame = decode_rect(item.get("frame"))
    if frame is None:
        if item.get("frame") is not None:
            warnings.append(f"frame 无法解析（真机校准点）：class={class_name}")
        left_f, top_f = origin
        width_f = height_f = 0.0
        bounds_origin = (0.0, 0.0)
    else:
        # frameToRoot = frame.origin - 父级 bounds.origin + 父级 frameToRoot（对齐官方
        # LookinDisplayItem+LookinClient calculateFrameToRoot：bounds.origin ≠ 0 的滚动
        # 容器里，子节点 frame 相对 bounds 原点，需先扣除 contentOffset 类偏移）
        left_f = frame["x"] - parent_bounds_origin[0] + origin[0]
        top_f = frame["y"] - parent_bounds_origin[1] + origin[1]
        width_f = frame["width"]
        height_f = frame["height"]
        item_bounds = decode_rect(item.get("bounds"))
        bounds_origin = (item_bounds["x"], item_bounds["y"]) if item_bounds else (0.0, 0.0)
    attrs["bounds"] = "[{},{}][{},{}]".format(
        max(0, round_px(left_f * scale)),
        max(0, round_px(top_f * scale)),
        max(0, round_px((left_f + width_f) * scale)),
        max(0, round_px((top_f + height_f) * scale)),
    )
    is_hidden = item.get("hidden") is True
    alpha = item.get("alpha")
    alpha_f = float(alpha) if isinstance(alpha, (int, float)) and not isinstance(alpha, bool) else 1.0
    if is_hidden:
        attrs["hidden"] = "true"
    if alpha_f < 0.99:
        attrs["alpha"] = _format_value(alpha_f)
    extra = build_extras(item, attr_groups_by_oid)
    if extra.get("ivar"):
        attrs["ivar"] = str(extra["ivar"])
    if extra.get("ivar") or extra.get("groups"):
        extras_by_key[key] = extra
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
            _build_node(element, child, f"{key}.{child_index}", (left_f, top_f), bounds_origin, scale, attr_groups_by_oid, warnings, extras_by_key)


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
