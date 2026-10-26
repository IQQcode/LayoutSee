"""Lookin 属性值归一化：把 210 响应里的属性组整理为契约 extras 结构。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
- 值类型枚举（LookinAttrType.h）：12=Float 13=Double 14=BOOL 15=Sel 16=Class
  17=CGPoint 18=CGVector 19=CGSize 20=CGRect 21=CGAffineTransform 22=UIEdgeInsets
  23=UIOffset 24=NSString 25/26=Enum 27=UIColor(rgba 数组) 28=CustomObj(按 identifier 解析)
- NSValue 在 NSKeyedArchiver 里落为 {"NS.special": code, ...字符串}：
  1=NSPoint("{x, y}") 2=CGSize("{w, h}") 3=CGRect("{{x, y}, {w, h}}") 11=UIEdgeInsets(四键浮点)
- extras 值统一为 {"kind": ...} 结构（string/number/boolean/enum/color/point/size/rect/
  edges/chain/nil/raw），展示格式化由 Web 端完成，Core 不做文案。
"""
from __future__ import annotations

import re

from .archiver import decode_rect
from ._utils import as_int

# NS.special → 几何 kind（未识别的 special 走 raw 兜底）
_NS_SPECIAL_KINDS = {1: "point", 2: "size", 3: "rect", 11: "edges"}

_POINT_STRING = re.compile(r"^\{\s*([-+\d.eE]+)\s*,\s*([-+\d.eE]+)\s*\}$")
# 视图/图层自带的 ivar（如 UILabel.layer 的 _layer）对定位无意义，遴选时跳过
_SYSTEM_IVAR_NAMES = {"_layer"}


def _floats(text: str) -> list[float] | None:
    parts = [part for part in re.split(r"[\s,]+", text.strip("{} \t")) if part]
    try:
        return [float(part) for part in parts]
    except ValueError:
        return None


def _point_value(text: object) -> dict[str, object] | None:
    if not isinstance(text, str):
        return None
    numbers = _floats(text)
    if numbers is None or len(numbers) != 2:
        return None
    return {"kind": "point", "x": numbers[0], "y": numbers[1]}


def _size_value(text: object) -> dict[str, object] | None:
    if not isinstance(text, str):
        return None
    numbers = _floats(text)
    if numbers is None or len(numbers) != 2:
        return None
    return {"kind": "size", "width": numbers[0], "height": numbers[1]}


def _edges_value(payload: dict[object, object]) -> dict[str, object] | None:
    edges: dict[str, float] = {}
    for name in ("top", "left", "bottom", "right"):
        value = payload.get(f"NS.edgeval.{name}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            edges[name] = float(value)
        else:
            return None
    return {"kind": "edges", **edges}


def normalize_attr_value(attr: dict[object, object]) -> dict[str, object]:
    """单个 LookinAttribute 的 value → 契约 extras 值结构（未知形态 raw 兜底，不报错）。"""
    value = attr.get("value")
    attr_type = as_int(attr.get("attrType")) or 0
    if value is None:
        return {"kind": "nil"}
    if isinstance(value, dict):
        special = as_int(value.get("NS.special"))
        kind = _NS_SPECIAL_KINDS.get(special) if special is not None else None
        if kind == "rect":
            rect = decode_rect(value.get("NS.rectval"))
            if rect is not None:
                return {"kind": "rect", **rect}
        elif kind == "point":
            point = _point_value(value.get("NS.pointval"))
            if point is not None:
                return point
        elif kind == "size":
            size = _size_value(value.get("NS.sizeval"))
            if size is not None:
                return size
        elif kind == "edges":
            edges = _edges_value(value)
            if edges is not None:
                return edges
        return {"kind": "raw", "value": str(value)}
    if isinstance(value, bool):
        return {"kind": "boolean", "value": value}
    if isinstance(value, (int, float)):
        if attr_type in (25, 26):  # EnumInt / EnumLong
            return {"kind": "enum", "value": value}
        return {"kind": "number", "value": value}
    if isinstance(value, str):
        return {"kind": "string", "value": value}
    if isinstance(value, list):
        if value and all(isinstance(row, list) for row in value):
            return {"kind": "chain", "value": [[str(name) for name in row] for row in value]}
        if len(value) == 4 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
            return {"kind": "color", "rgba": [float(item) for item in value]}
        return {"kind": "chain", "value": [str(item) for item in value]}
    return {"kind": "raw", "value": str(value)}


def normalize_attr_groups(groups: object) -> list[dict[str, object]]:
    """属性组列表 → extras.groups（空组/空节剔除，未知结构静默跳过）。"""
    result: list[dict[str, object]] = []
    if not isinstance(groups, list):
        return result
    for group in groups:
        if not isinstance(group, dict):
            continue
        sections_out: list[dict[str, object]] = []
        sections = group.get("attrSections")
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                attributes: list[dict[str, object]] = []
                raw_attrs = section.get("attributes")
                if isinstance(raw_attrs, list):
                    for attr in raw_attrs:
                        if isinstance(attr, dict) and attr.get("identifier"):
                            attributes.append({
                                "identifier": str(attr["identifier"]),
                                "type": as_int(attr.get("attrType")) or 0,
                                "value": normalize_attr_value(attr),
                            })
                if attributes:
                    sections_out.append({
                        "identifier": str(section.get("identifier") or ""),
                        "attributes": attributes,
                    })
        if sections_out:
            result.append({
                "identifier": str(group.get("identifier") or ""),
                "sections": sections_out,
            })
    return result


def best_ivar(item: dict[object, object]) -> str | None:
    """从 viewObject/layerObject 的 ivarTraces 里挑最有定位意义的 ivar 名。

    TraceManager 会把「宿主对象哪个 ivar 引用了本视图」写成 trace（如 _titleLabel）；
    图层自带的 _layer 无定位价值，只剩系统名时宁可返回 None，不硬凑。
    viewObject 优先（自定义视图的 ivar 命名通常挂在 view 上）。
    """
    for key in ("viewObject", "layerObject"):
        obj = item.get(key)
        traces = obj.get("ivarTraces") if isinstance(obj, dict) else None
        if not isinstance(traces, list):
            continue
        for trace in traces:
            name = trace.get("ivarName") if isinstance(trace, dict) else None
            if isinstance(name, str) and name and name not in _SYSTEM_IVAR_NAMES:
                return name
    return None


def build_extras(item: dict[object, object], attr_groups_by_oid: dict[int, list[object]]) -> dict[str, object]:
    """单节点 extras：{"ivar": str|None, "groups": [...]}（无任何内容时 groups 为空列表）。"""
    groups: list[object] = []
    for key in ("layerObject", "viewObject"):
        obj = item.get(key)
        oid = as_int(obj.get("oid")) if isinstance(obj, dict) else None
        if oid is not None and attr_groups_by_oid.get(oid):
            groups = attr_groups_by_oid[oid]
            break
    return {"ivar": best_ivar(item), "groups": normalize_attr_groups(groups)}
