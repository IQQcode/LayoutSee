"""LookinClient：请求编排（握手 / App 信息 / 层级 / 属性详情）。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
- 请求类型（LookinDefines.h）：Ping=200 / App=201 / Hierarchy=202 / HierarchyDetails=203 / AllAttrGroups=210
- 请求载荷：LookinConnectionAttachment{"0": data, "1": dataType}（请求侧 dataType 恒 0）
- 响应载荷：LookinConnectionResponseAttachment{"0": data, "1": dataType, "lookinServerVersion",
  "error", "dataTotalCount", "currentDataCount", "appIsInBackground"}
- lookinServerVersion 必须 ==7（对应 LookinServer 1.2.8），否则抛 LOOKIN_VERSION_MISMATCH
- 请求超时：Ping/App 0.5s（探测阶段）、Hierarchy/HierarchyDetails 5s；超时抛 OPERATION_TIMEOUT
- 响应 attach.error 非 None 抛 LOOKIN_UNAVAILABLE
- HierarchyDetails 分批：按 dataTotalCount/currentDataCount 判定完成，attrGroups 按 oid 宽松归并、
  图片类字段丢弃
"""
from __future__ import annotations

import socket

from ..errors import CoreError
from . import archiver, peertalk
from ._utils import as_int

REQUEST_PING = 200
REQUEST_APP = 201
REQUEST_HIERARCHY = 202
REQUEST_HIERARCHY_DETAILS = 203
REQUEST_ALL_ATTR_GROUPS = 210

SUPPORTED_SERVER_VERSION = 7
PROBE_TIMEOUT = 0.5
REQUEST_TIMEOUT = 5.0
ATTR_TIMEOUT = 2.0  # AllAttrGroups 单节点超时：回环 RTT 毫秒级，超时视为对象不可用
MAX_BATCHES = 64

# LookinError 错误码（LookinDefines.h）：对象不存在（oid 查表失败，逐节点拉属性的常态降级）
LOOKIN_ERR_CODE_OBJ_NOT_FOUND = -500

# attrGroups 聚合认可的组字段名（小写、去下划线后比较；真机校准点）
_GROUP_KEYS = {"attributesgroups", "attrgroups", "groups", "attrs", "attrsections"}


def _normalize_app_info(payload: object) -> dict[str, object]:
    """LookinAppInfo 数字键 → 业务键（键名语义见上方校准注释）。"""
    p = payload if isinstance(payload, dict) else {}
    return {
        "appName": p.get("5"),
        "appBundleIdentifier": p.get("appBundleIdentifier"),
        "deviceDescription": p.get("3"),
        "osDescription": p.get("4"),
        "deviceType": p.get("8"),
        "screenWidth": p.get("6"),
        "screenHeight": p.get("7"),
        "screenScale": p.get("screenScale"),
    }

# 请求参数与响应键名（真机校准点，2026-10-25 依 iOS 27 模拟器实测校准）：
# - App(201) 请求 data 必须是 NSDictionary：{"needImages": bool, "local": []}，否则 LookinServer 回 Inner error
# - Hierarchy(202) 请求 data 建议 {"clientVersion": "1.2.8"}
# - LookinAppInfo 响应键为数字：1=screenshot 2=appIcon 3=deviceDescription 4=osDescription
#   5=appName 6=screenWidth 7=screenHeight 8=deviceType；bundleId/scale 等用属性名
# - LookinHierarchyInfo 响应键：1=displayItems 2=appInfo 3=colorAlias 4=collapsedClassList


class LookinClient:
    """单连接 Lookin 客户端：tag 递增，服务端按请求的 type+tag 回显响应。"""

    def __init__(self, stream: socket.socket) -> None:
        self.stream = stream
        self._tag = 0

    def ping(self, warnings_out: list[str] | None = None) -> int:
        """握手：返回 lookinServerVersion（调用方语义上应已通过 _decode_response 校验 ==7）。

        解码 warnings 经 warnings_out 外送（None 则丢弃），供探测方并入诊断记录。
        """
        attach, warnings = self._request(REQUEST_PING, timeout=PROBE_TIMEOUT)
        if warnings_out is not None:
            warnings_out.extend(warnings)
        version = attach.get("lookinServerVersion")
        if not isinstance(version, int) or isinstance(version, bool):
            raise CoreError("LOOKIN_UNAVAILABLE", "Ping 响应缺少 lookinServerVersion。")
        return version

    def app_info(self) -> dict[str, object]:
        """App 信息（请求参数按 LookinServer 要求必须为 dict），返回规整后的业务键。"""
        attach, warnings = self._request(
            REQUEST_APP,
            timeout=PROBE_TIMEOUT,
            data={"needImages": False, "local": []},
        )
        result = _normalize_app_info(attach.get("0"))
        result.update({
            "appIsInBackground": attach.get("appIsInBackground"),
            "serverVersion": attach.get("lookinServerVersion"),
            "warnings": warnings,
        })
        return result

    def hierarchy(self) -> dict[str, object]:
        """层级树：{"displayItems": [...], "appInfo": {规整键}|{}, "warnings": [...]}。

        树节点为 LookinDisplayItem（属性名键：subitems/frame/viewObject/layerObject/attributesGroupList...）。
        注意 attributesGroupList 在 static 树里为空，属性组需逐节点 AllAttrGroups 获取。
        """
        attach, warnings = self._request(
            REQUEST_HIERARCHY,
            timeout=REQUEST_TIMEOUT,
            data={"clientVersion": "1.2.8"},
        )
        payload = attach.get("0") if isinstance(attach.get("0"), dict) else {}
        return {
            "displayItems": payload.get("1") if isinstance(payload.get("1"), list) else [],
            "appInfo": _normalize_app_info(payload.get("2")),
            "warnings": warnings,
        }

    def all_attr_groups(self, oid: int) -> dict[str, object]:
        """按 oid 拉取属性组：{"attrGroups": [...], "warnings": [...]}。

        对象不存在（ObjNotFound，LookinError -500）是常态（layer 未注册/已释放），返回空列表。
        """
        try:
            attach, warnings = self._request(REQUEST_ALL_ATTR_GROUPS, timeout=ATTR_TIMEOUT, data=int(oid))
        except CoreError as error:
            error_detail = error.details.get("error") if isinstance(error.details, dict) else None
            code = error_detail.get("code") if isinstance(error_detail, dict) else None
            if code == LOOKIN_ERR_CODE_OBJ_NOT_FOUND:
                return {"attrGroups": [], "warnings": [f"oid={oid} 对象不存在（已释放或未注册）。"]}
            raise
        data = attach.get("0")
        return {"attrGroups": data if isinstance(data, list) else [], "warnings": warnings}

    def hierarchy_details(self) -> dict[str, object]:
        """分批读取 HierarchyDetails 并宽松聚合（attrGroups 按 oid 归并、图片字段丢弃）。"""
        tag = self._next_tag()
        batches: list[object] = []
        warnings: list[str] = []
        total: int | None = None
        current = 0
        first = True
        while True:
            if first:
                attach, batch_warnings = self._request(REQUEST_HIERARCHY_DETAILS, timeout=REQUEST_TIMEOUT, tag=tag)
                first = False
            else:
                attach, batch_warnings = self._read_response(REQUEST_HIERARCHY_DETAILS, tag, REQUEST_TIMEOUT)
            warnings.extend(batch_warnings)
            batches.append(attach.get("0"))
            batch_total = as_int(attach.get("dataTotalCount"))
            batch_current = as_int(attach.get("currentDataCount"))
            if batch_total is not None and batch_total > 0:
                total = batch_total
            if batch_current is not None:
                current = batch_current
            if total is None or current >= total:
                break  # 无分批信息视为单批；分批读满即完成
            if len(batches) >= MAX_BATCHES:
                warnings.append(f"分批数量超过防御上限 {MAX_BATCHES}，提前截断。")
                break
        return merge_hierarchy_details(batches, warnings)

    def _next_tag(self) -> int:
        self._tag += 1
        return self._tag

    def _request(
        self,
        request_type: int,
        *,
        timeout: float,
        data: object = None,
        tag: int | None = None,
    ) -> tuple[dict[str, object], list[str]]:
        """发送一帧请求并读取第一帧响应，返回 (响应 attachment, warnings)。"""
        actual_tag = tag if tag is not None else self._next_tag()
        try:
            self.stream.settimeout(timeout)
            peertalk.write_frame(self.stream, request_type, actual_tag, archiver.encode_attachment(data))
            frame_type, frame_tag, body = peertalk.read_frame(self.stream)
        except socket.timeout as error:
            raise self._timeout_error(request_type, timeout) from error
        self._check_frame(request_type, actual_tag, frame_type, frame_tag)
        return self._decode_response(body)

    def _read_response(self, request_type: int, tag: int, timeout: float) -> tuple[dict[str, object], list[str]]:
        """读取后续分批响应帧（不发送请求）。"""
        try:
            self.stream.settimeout(timeout)
            frame_type, frame_tag, body = peertalk.read_frame(self.stream)
        except socket.timeout as error:
            raise self._timeout_error(request_type, timeout) from error
        self._check_frame(request_type, tag, frame_type, frame_tag)
        return self._decode_response(body)

    @staticmethod
    def _check_frame(request_type: int, tag: int, frame_type: int, frame_tag: int) -> None:
        if frame_type != request_type or frame_tag != tag:
            raise CoreError(
                "LOOKIN_UNAVAILABLE",
                f"响应帧 type/tag 不匹配：期望 ({request_type},{tag})，收到 ({frame_type},{frame_tag})。",
                details={"expectedType": request_type, "expectedTag": tag, "actualType": frame_type, "actualTag": frame_tag},
            )

    @staticmethod
    def _decode_response(body: bytes) -> tuple[dict[str, object], list[str]]:
        attach, warnings = archiver.unarchive(body)
        if not isinstance(attach, dict):
            raise CoreError("LOOKIN_UNAVAILABLE", "响应载荷不是 LookinConnectionResponseAttachment 结构。")
        version = attach.get("lookinServerVersion")
        if version is not None and version != SUPPORTED_SERVER_VERSION:
            raise CoreError(
                "LOOKIN_VERSION_MISMATCH",
                f"LookinServer 版本不兼容：{version}（需要 {SUPPORTED_SERVER_VERSION}，对应 LookinServer 1.2.8）。",
                details={"serverVersion": version},
            )
        error = attach.get("error")
        if error is not None:
            description = error.get("description") if isinstance(error, dict) else str(error)
            raise CoreError(
                "LOOKIN_UNAVAILABLE",
                f"LookinServer 返回错误：{description}",
                details={"error": error},
            )
        return attach, warnings

    @staticmethod
    def _timeout_error(request_type: int, timeout: float) -> CoreError:
        return CoreError(
            "OPERATION_TIMEOUT",
            f"Lookin 请求超时（{timeout}s）：type={request_type}。",
            retryable=True,
            details={"requestType": request_type, "timeout": timeout},
        )


def merge_hierarchy_details(batches: list[object], warnings: list[str]) -> dict[str, object]:
    """宽松聚合 HierarchyDetails 各批次 data（真机校准点）：

    - 收集所有批次原始结构进合并结果
    - 丢弃图片类字段：值类名链含 Image 的 dict，以及原始 NSData bytes 载荷
      （层级详情里的大块二进制只可能是图片，避免落盘/转发）
    - attrGroups 按能找到的 oid 维度归并
    """
    cleaned_batches: list[object] = []
    attr_groups_by_oid: dict[int, list[object]] = {}
    dropped = 0
    for batch in batches:
        cleaned, count = _strip_image_fields(batch)
        dropped += count
        cleaned_batches.append(cleaned)
        _collect_attr_groups(cleaned, attr_groups_by_oid)
    if dropped:
        warnings.append(f"已丢弃 {dropped} 个图片字段。")
    return {
        "attrGroupsByOid": attr_groups_by_oid,
        "batches": cleaned_batches,
        "droppedImageFieldCount": dropped,
        "warnings": warnings,
    }


def _strip_image_fields(value: object) -> tuple[object, int]:
    if isinstance(value, dict):
        classes = value.get("_classes")
        if isinstance(classes, list) and any("image" in str(name).lower() for name in classes):
            return None, 1
        cleaned: dict[str, object] = {}
        dropped = 0
        for key, item in value.items():
            if isinstance(item, (bytes, bytearray)):
                dropped += 1  # NSData 载荷（图片二进制）
                continue
            cleaned_item, count = _strip_image_fields(item)
            cleaned[str(key)] = cleaned_item
            dropped += count
        return cleaned, dropped
    if isinstance(value, list):
        cleaned_list: list[object] = []
        dropped = 0
        for item in value:
            cleaned_item, count = _strip_image_fields(item)
            cleaned_list.append(cleaned_item)
            dropped += count
        return cleaned_list, dropped
    if isinstance(value, (bytes, bytearray)):
        return None, 1
    return value, 0


def _collect_attr_groups(value: object, out: dict[int, list[object]]) -> None:
    """从批次数据中宽松抽取 {oid: [attrGroup...]}，兼容多种真实结构（真机校准点）：
    - {oid: [group...]}（键为 int 或数字字符串）
    - [{"oid": 123, "attributesGroups": [...]}] / {"oid": 123, "attrGroups": [...]}
    """
    if isinstance(value, dict):
        pair = _oid_groups_of(value)
        if pair is not None:
            oid, groups = pair
            out.setdefault(oid, []).extend(groups)
            return  # 命中 oid 条目后不再下钻，避免重复归并
        for key, item in value.items():
            oid = as_int(key)
            if oid is not None and _looks_like_groups(item):
                out.setdefault(oid, []).extend(_as_group_list(item))
            else:
                _collect_attr_groups(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_attr_groups(item, out)


def _oid_groups_of(value: dict[object, object]) -> tuple[int, list[object]] | None:
    oid = as_int(value.get("oid"))
    if oid is None:
        return None
    for key in value:
        if str(key).lower().replace("_", "") in _GROUP_KEYS:
            return oid, _as_group_list(value[key])
    return None


def _looks_like_groups(item: object) -> bool:
    if isinstance(item, list):
        return bool(item) and all(isinstance(group, dict) for group in item)
    return isinstance(item, dict)


def _as_group_list(item: object) -> list[object]:
    if isinstance(item, list):
        return [group for group in item if isinstance(group, dict)]
    return [item] if isinstance(item, dict) else []


