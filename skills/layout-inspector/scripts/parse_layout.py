#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android 运行时布局快照解析器。

支持两种输入：
1. LayoutInspectorV2-Pro 导出的 .liv2 文件。先解包 Java ObjectOutputStream 外层，
   再解码 ViewHierarchyEncoder V2 的类型流、字符串表和嵌套 View Map，恢复真实层级。
   完整解析失败时保留旧固定 key 扫描器作为兼容兜底，并明确标注近似层级。
2. uiautomator dump 的 hierarchy XML，保留 XML 中的真实父子关系和常用属性。

输出可读控件树和 JSON。坐标统一为 [left, top, right, bottom] 像素。

用法：
    python3 parse_layout.py <file.liv2|file.xml> [--json out.json] [--filter editor_bar]
        [--max-depth N] [--json-only]
"""
import argparse
import json
import re
import struct
import xml.etree.ElementTree as ET


# ---------- .liv2 (LayoutInspectorV2-Pro) ----------

JAVA_STREAM_MAGIC = b"\xac\xed\x00\x05"
TC_BLOCKDATA = 0x77
TC_BLOCKDATALONG = 0x7A
TC_RESET = 0x79
TC_ENDBLOCKDATA = 0x78

SIG_BOOLEAN = ord("Z")
SIG_BYTE = ord("B")
SIG_SHORT = ord("S")
SIG_INT = ord("I")
SIG_LONG = ord("J")
SIG_FLOAT = ord("F")
SIG_DOUBLE = ord("D")
SIG_STRING = ord("R")
SIG_MAP = ord("M")

# 仅用于完整解析失败后的旧样本兼容路径，不代表跨版本稳定协议。
LEGACY_KEY_CLASS = 3
LEGACY_KEY_RESID = 5
LEGACY_KEY_LEFT = 8
LEGACY_KEY_RIGHT = 9
LEGACY_KEY_TOP = 10
LEGACY_KEY_BOTTOM = 11


class Liv2ParseError(ValueError):
    pass


class ByteReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def remaining(self):
        return len(self.data) - self.pos

    def read(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise Liv2ParseError(f"数据不足: pos={self.pos}, size={size}")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def unpack(self, fmt):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.read(size))[0]



def _read_java_block_stream(data):
    """提取 ObjectOutputStream 顶层 primitive block data 的逻辑字节流。"""
    if not data.startswith(JAVA_STREAM_MAGIC):
        raise Liv2ParseError("缺少 Java 序列化流头 ac ed 00 05")

    reader = ByteReader(data[4:])
    payload = bytearray()
    while reader.remaining():
        token = reader.unpack(">B")
        if token == TC_BLOCKDATA:
            payload.extend(reader.read(reader.unpack(">B")))
        elif token == TC_BLOCKDATALONG:
            length = reader.unpack(">I")
            payload.extend(reader.read(length))
        elif token in (TC_RESET, TC_ENDBLOCKDATA):
            continue
        else:
            raise Liv2ParseError(
                f"不支持的 Java 序列化 token 0x{token:02x}, offset={reader.pos + 3}"
            )
    return bytes(payload)



def _decode_java_utf(data):
    # writeUTF 使用 modified UTF-8。常见 Android 标题可按 UTF-8 解码，空字符需单独还原。
    return data.replace(b"\xc0\x80", b"\x00").decode("utf-8", errors="replace")



def _unwrap_liv2(data):
    primitive = ByteReader(_read_java_block_stream(data))
    options_length = primitive.unpack(">H")
    options_text = _decode_java_utf(primitive.read(options_length))
    try:
        options = json.loads(options_text)
    except json.JSONDecodeError as exc:
        raise Liv2ParseError(f"采集选项 JSON 无效: {exc}") from exc

    hierarchy_length = primitive.unpack(">i")
    if hierarchy_length < 0:
        raise Liv2ParseError("hierarchy 长度为负数")
    hierarchy = primitive.read(hierarchy_length)

    preview_length = primitive.unpack(">i")
    if preview_length < 0:
        raise Liv2ParseError("preview 长度为负数")
    preview = primitive.read(preview_length)
    if primitive.remaining():
        raise Liv2ParseError(f"外层容器存在 {primitive.remaining()} 个未消费字节")
    return options, hierarchy, preview



def _read_v2_string(reader):
    length = reader.unpack(">h")
    if length < 0:
        raise Liv2ParseError(f"V2 字符串长度为负数: {length}")
    return reader.read(length).decode("utf-8", errors="replace")



def _read_v2_object(reader):
    if not reader.remaining():
        raise Liv2ParseError("V2 对象意外结束")
    sig = reader.unpack(">B")
    if sig == SIG_BOOLEAN:
        return reader.unpack(">B") != 0
    if sig == SIG_BYTE:
        return reader.unpack(">b")
    if sig == SIG_SHORT:
        return reader.unpack(">h")
    if sig == SIG_INT:
        return reader.unpack(">i")
    if sig == SIG_LONG:
        return reader.unpack(">q")
    if sig == SIG_FLOAT:
        return reader.unpack(">f")
    if sig == SIG_DOUBLE:
        return reader.unpack(">d")
    if sig == SIG_STRING:
        return _read_v2_string(reader)
    if sig == SIG_MAP:
        result = {}
        while True:
            key = _read_v2_object(reader)
            if not isinstance(key, int) or isinstance(key, bool):
                raise Liv2ParseError(f"V2 Map key 不是 short: {key!r}")
            if key == 0:
                return result
            result[key] = _read_v2_object(reader)
    raise Liv2ParseError(f"未知 V2 类型标记 0x{sig:02x}, offset={reader.pos - 1}")



def _decode_v2_hierarchy(data):
    reader = ByteReader(data)
    objects = []
    while reader.remaining():
        objects.append(_read_v2_object(reader))
    maps = [value for value in objects if isinstance(value, dict)]
    if len(maps) < 2:
        raise Liv2ParseError("V2 hierarchy 缺少根 View Map 或字符串表")
    string_table = maps[-1]
    if not all(isinstance(key, int) and isinstance(value, str)
               for key, value in string_table.items()):
        raise Liv2ParseError("V2 hierarchy 最后一个 Map 不是字符串表")
    return maps[0], string_table



def _first_property(props, *names, default=None):
    for name in names:
        if name in props:
            return props[name]
    return default



def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default



def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default



def _property_names(view_map, string_table):
    props = {}
    for key, value in view_map.items():
        full_name = string_table.get(key)
        if full_name is None:
            continue
        props[full_name] = value
        if ":" in full_name:
            props.setdefault(full_name.split(":", 1)[1], value)
    return props



def _build_v2_nodes(root_map, string_table):
    nodes = []

    def walk(view_map, depth, parent_origin=(0, 0), parent_scroll=(0, 0)):
        props = _property_names(view_map, string_table)
        fqcn = str(props.get("meta:__name__", ""))
        if not fqcn:
            raise Liv2ParseError("View Map 缺少 meta:__name__")

        left = _as_int(_first_property(props, "mLeft", "layout:mLeft", "left"))
        top = _as_int(_first_property(props, "mTop", "layout:mTop", "top"))
        width = _as_int(_first_property(
            props, "getWidth()", "layout:getWidth()", "width", default=0
        ))
        height = _as_int(_first_property(
            props, "getHeight()", "layout:getHeight()", "height", default=0
        ))
        translation_x = _as_float(_first_property(
            props, "getTranslationX", "drawing:getTranslationX()", "translationX", default=0
        ))
        translation_y = _as_float(_first_property(
            props, "getTranslationY", "drawing:getTranslationY()", "translationY", default=0
        ))
        abs_left = parent_origin[0] - parent_scroll[0] + left + translation_x
        abs_top = parent_origin[1] - parent_scroll[1] + top + translation_y

        node = {
            "class": fqcn.split(".")[-1],
            "fqcn": fqcn,
            "depth": depth,
            "bounds": [round(abs_left), round(abs_top),
                       round(abs_left + width), round(abs_top + height)],
        }

        labels = []
        for name in ("id", "mID", "contentDescription",
                     "accessibility:getContentDescription()", "text:mText", "text"):
            value = props.get(name)
            if value not in (None, "", "null", "NO_ID"):
                text = str(value)
                if text not in labels:
                    labels.append(text)
        if labels:
            node["labels"] = labels

        flags = []
        for output_name, property_names in (
            ("clickable", ("isClickable()", "clickable")),
            ("scrollable", ("isScrollContainer()", "scrollable")),
            ("selected", ("isSelected()", "selected")),
            ("enabled", ("isEnabled()", "enabled")),
        ):
            value = _first_property(props, *property_names)
            if value is True or str(value).lower() == "true":
                flags.append(output_name)
        if flags:
            node["flags"] = flags
        nodes.append(node)

        child_entries = []
        prefix = "meta:__child__"
        for name, value in props.items():
            if name.startswith(prefix) and isinstance(value, dict):
                try:
                    index = int(name[len(prefix):])
                except ValueError:
                    continue
                child_entries.append((index, value))
        child_entries.sort(key=lambda item: item[0])

        expected = _as_int(props.get("meta:__childCount__"), len(child_entries))
        if expected != len(child_entries):
            raise Liv2ParseError(
                f"{fqcn} 子节点数量不一致: expected={expected}, actual={len(child_entries)}"
            )

        scroll_x = _as_int(_first_property(props, "mScrollX", "scrolling:mScrollX", "scrollX"))
        scroll_y = _as_int(_first_property(props, "mScrollY", "scrolling:mScrollY", "scrollY"))
        for _, child_map in child_entries:
            walk(child_map, depth + 1, (abs_left, abs_top), (scroll_x, scroll_y))

    walk(root_map, 0)
    return nodes



def _legacy_read_string(data, pos):
    if pos + 2 > len(data):
        raise Liv2ParseError("旧扫描器读取字符串长度越界")
    length = struct.unpack_from(">H", data, pos)[0]
    pos += 2
    if pos + length > len(data):
        raise Liv2ParseError("旧扫描器读取字符串内容越界")
    return data[pos:pos + length].decode("utf-8", errors="replace"), pos + length



def _parse_liv2_legacy(data, error):
    """旧固定 key 扫描器，仅作为异常文件兼容兜底。"""
    title = None
    match = re.search(rb'"title"\s*:\s*"([^"]+)"', data[:512])
    if match:
        title = match.group(1).decode("utf-8", errors="replace")

    nodes = []
    pos = 0
    while pos < len(data) - 4:
        if data[pos:pos + 4] == b"S\x00\x03R":
            try:
                fqcn, prop_pos = _legacy_read_string(data, pos + 4)
            except Liv2ParseError:
                pos += 1
                continue
            if not re.match(r"^[a-zA-Z_][\w.$]*\.[A-Za-z_]\w*$", fqcn):
                pos += 1
                continue
            props = {}
            while prop_pos < len(data) - 3 and data[prop_pos] == SIG_SHORT:
                key = struct.unpack_from(">H", data, prop_pos + 1)[0]
                if key == LEGACY_KEY_CLASS:
                    break
                value_type = data[prop_pos + 3]
                next_pos = prop_pos + 4
                try:
                    if value_type == SIG_INT:
                        props[key] = struct.unpack_from(">i", data, next_pos)[0]
                        next_pos += 4
                    elif value_type == SIG_FLOAT:
                        props[key] = struct.unpack_from(">f", data, next_pos)[0]
                        next_pos += 4
                    elif value_type == SIG_STRING:
                        props[key], next_pos = _legacy_read_string(data, next_pos)
                    elif value_type == SIG_SHORT:
                        props[key] = struct.unpack_from(">h", data, next_pos)[0]
                        next_pos += 2
                    elif value_type == SIG_BOOLEAN:
                        props[key] = data[next_pos] != 0
                        next_pos += 1
                    else:
                        break
                except (Liv2ParseError, struct.error):
                    break
                prop_pos = next_pos

            coords = [props.get(key) for key in (
                LEGACY_KEY_LEFT, LEGACY_KEY_TOP, LEGACY_KEY_RIGHT, LEGACY_KEY_BOTTOM
            )]
            if (not fqcn.endswith("LayoutParams") and "Resources$" not in fqcn
                    and None not in coords):
                node = {
                    "class": fqcn.split(".")[-1],
                    "fqcn": fqcn,
                    "bounds": coords,
                }
                resource_id = props.get(LEGACY_KEY_RESID)
                if resource_id not in (None, "", "NO_ID"):
                    node["labels"] = [str(resource_id)]
                nodes.append(node)
            pos = max(prop_pos, pos + 1)
            continue
        pos += 1

    if not nodes:
        raise Liv2ParseError(f"完整解析失败且旧扫描器未找到节点: {error}")
    infer_liv2_depth(nodes)
    return {
        "title": title,
        "source": "liv2",
        "parser": "legacy-key-scan",
        "hierarchy": "approximate",
        "warning": f"完整 V2 解析失败，已使用固定 key 兜底: {error}",
        "nodes": nodes,
    }



def parse_liv2(path: str):
    with open(path, "rb") as file_obj:
        data = file_obj.read()
    try:
        options, hierarchy, preview = _unwrap_liv2(data)
        version = str(options.get("version", ""))
        if version != "2":
            raise Liv2ParseError(f"暂不支持 LIV2 hierarchy 协议版本: {version or '未知'}")
        root_map, string_table = _decode_v2_hierarchy(hierarchy)
        nodes = _build_v2_nodes(root_map, string_table)
        return {
            "title": options.get("title") or None,
            "source": "liv2",
            "parser": "v2-structured",
            "hierarchy": "exact",
            "protocolVersion": version,
            "previewBytes": len(preview),
            "nodes": nodes,
        }
    except (Liv2ParseError, struct.error, UnicodeDecodeError) as exc:
        return _parse_liv2_legacy(data, str(exc))



# ---------- uiautomator dump XML ----------

def _parse_bounds_attr(b: str):
    # 形如 "[0,80][1080,230]"
    m = re.findall(r"-?\d+", b or "")
    if len(m) == 4:
        return [int(x) for x in m]
    return []


def parse_uiautomator_xml(path: str):
    tree = ET.parse(path)
    root = tree.getroot()
    nodes = []

    def walk(el, depth):
        cls = el.attrib.get("class", el.tag)
        item = {
            "class": cls.split(".")[-1] if cls else el.tag,
            "fqcn": cls,
            "depth": depth,
            "bounds": _parse_bounds_attr(el.attrib.get("bounds", "")),
        }
        rid = el.attrib.get("resource-id", "")
        text = el.attrib.get("text", "")
        cd = el.attrib.get("content-desc", "")
        labels = [x for x in (rid, text, cd) if x]
        if labels:
            item["labels"] = labels
        for k in ("clickable", "scrollable", "selected"):
            if el.attrib.get(k) == "true":
                item.setdefault("flags", []).append(k)
        nodes.append(item)
        for child in list(el):
            walk(child, depth + 1)

    for child in list(root):
        walk(child, 0)
    return {"title": None, "source": "uiautomator", "nodes": nodes}


# ---------- liv2 近似层级（基于坐标包含 + 出现顺序）----------

def infer_liv2_depth(nodes):
    """仅为旧扫描器产生的扁平节点推断近似层级。

    完整 V2 解析会通过 meta:__child__N 恢复真实层级，不调用本函数。旧扫描器无法
    保留嵌套 Map，只能用 bounds 包含关系提供阅读辅助，兄弟节点重叠时可能不准确。
    """
    def contains(outer, inner):
        if not outer or not inner or len(outer) < 4 or len(inner) < 4:
            return False
        return (outer[0] <= inner[0] and outer[1] <= inner[1]
                and outer[2] >= inner[2] and outer[3] >= inner[3]
                and outer != inner)

    stack = []  # [(bounds, depth)]
    for nd in nodes:
        b = nd.get("bounds")
        while stack and not contains(stack[-1][0], b):
            stack.pop()
        nd["depth"] = stack[-1][1] + 1 if stack else 0
        if b:
            stack.append((b, nd["depth"]))


# ---------- 渲染 ----------

def render_tree(parsed, filter_kw=None, max_depth=None):
    lines = []
    if parsed.get("title"):
        lines.append(f"# {parsed['title']}  (source: {parsed['source']})")
    else:
        lines.append(f"# layout snapshot  (source: {parsed['source']})")

    nodes = parsed["nodes"]
    matched = False
    for nd in nodes:
        depth = nd.get("depth", 0)
        if max_depth is not None and depth > max_depth:
            continue
        labels = nd.get("labels", [])
        # filter：命中 class 或任一 label 才输出
        if filter_kw:
            hay = " ".join([nd.get("fqcn", ""), nd.get("class", "")] + labels)
            if filter_kw.lower() not in hay.lower():
                continue
            matched = True
        indent = "  " * depth
        b = nd.get("bounds", [])
        bstr = f" bounds={b}" if b else ""
        lstr = f"  «{' / '.join(labels)}»" if labels else ""
        flags = nd.get("flags", [])
        fstr = f"  [{','.join(flags)}]" if flags else ""
        lines.append(f"{indent}{nd['class']}{bstr}{lstr}{fstr}")

    if filter_kw and not matched:
        lines.append(f"(未找到匹配 '{filter_kw}' 的节点)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="解析 Android 运行时布局快照 (.liv2 / uiautomator xml)")
    ap.add_argument("file", help=".liv2 或 uiautomator dump 的 xml 文件路径")
    ap.add_argument("--json", help="JSON 结构输出路径（不指定则只打印树）")
    ap.add_argument("--filter", help="只输出 class/id/文案 命中该关键字的节点（如 editor_bar）")
    ap.add_argument("--max-depth", type=int, default=None, help="最大渲染深度")
    ap.add_argument("--json-only", action="store_true", help="只输出 JSON 到标准输出")
    args = ap.parse_args()

    path = args.file
    if path.endswith(".xml"):
        parsed = parse_uiautomator_xml(path)
    else:
        head = open(path, "rb").read(64)
        if head.lstrip().startswith(b"<?xml") or head.lstrip().startswith(b"<hierarchy"):
            parsed = parse_uiautomator_xml(path)
        else:
            parsed = parse_liv2(path)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
        if not args.json_only:
            print(f"JSON 已写入: {args.json}  (共 {len(parsed['nodes'])} 个节点)")

    if args.json_only:
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    else:
        print(render_tree(parsed, filter_kw=args.filter, max_depth=args.max_depth))


if __name__ == "__main__":
    main()
