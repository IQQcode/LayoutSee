"""NSKeyedArchiver 二进制 plist 编解码（Lookin 载荷层）。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
Lookin 请求/响应载荷均为 NSKeyedArchiver 归档的 binary plist：
- 顶层容器：$archiver="NSKeyedArchiver"、$version=100000、$top={"root": UID 引用}、$objects 数组
- $objects 元素：字符串/数字原子、{"$classname","$classes"} 类骨架、{"$class",键:值} 实例
- nil 引用约定为 $objects[0]="$null"（即 UID(0)）
- 请求：LookinConnectionAttachment{"0": data（可为 None→null 引用）, "1": dataType（请求侧恒 0）}
- 响应：LookinConnectionResponseAttachment{"0": data, "1": dataType, "lookinServerVersion": int32,
  "error": NSError|nil, "dataTotalCount"/"currentDataCount": NSNumber, "appIsInBackground": bool}

解码是通用的：NSDictionary/NSArray/NSString/NSNumber/NSData/NSMutableData/NSSet/NSError 还原为
Python 类型；未知类骨架还原为 dict（附 "_classes" 键记录类名链）；引用缺失/循环容错为 None 并记
warning。CGRect 没有独立类型标记，用 decode_rect() 做多重格式宽松解码（真机校准点）。
"""
from __future__ import annotations

import plistlib
from plistlib import UID

from ..errors import CoreError

NULL_REF = "$null"
ARCHIVER_NAME = "NSKeyedArchiver"
ARCHIVER_VERSION = 100000

DATA_CLASS_CHAIN = ["NSData", "NSObject"]
DICT_CLASS_CHAIN = ["NSDictionary", "NSObject"]
ARRAY_CLASS_CHAIN = ["NSArray", "NSObject"]

# NSNumber 实例化形态的键名候选（Apple 通常直接存原子，实例形态少见，宽松兼容）
_NUMBER_VALUE_KEYS = (
    "NS.integervalue",
    "NS.longvalue",
    "NS.realvalue",
    "NS.realval",
    "NS.real",
    "NS.integer",
    "NS.int",
    "NS.double",
    "NS.float",
    "NS.boolval",
    "NS.number",
    "NS.string",
)

# NSError 键名（含常见变体，小写比较）
_ERROR_DOMAIN_KEYS = ("nsdomain", "domain")
_ERROR_CODE_KEYS = ("nscode", "code")
_ERROR_USERINFO_KEYS = ("nsuserinfo", "userinfo", "user_info")


class _Archiver:
    """最小化 NSKeyedArchiver 编码器：支持 None/bool/int/float/str/bytes/list/tuple/dict（不支持循环引用）。"""

    def __init__(self) -> None:
        self.objects: list[object] = [NULL_REF]
        self._atom_refs: dict[tuple[type, object], UID] = {}
        self._class_refs: dict[str, UID] = {}

    def new_object(self, entry: object) -> UID:
        ref = UID(len(self.objects))
        self.objects.append(entry)
        return ref

    def class_ref(self, class_name: str, class_chain: list[str]) -> UID:
        ref = self._class_refs.get(class_name)
        if ref is None:
            ref = self.new_object({"$classname": class_name, "$classes": list(class_chain)})
            self._class_refs[class_name] = ref
        return ref

    def reference(self, value: object) -> UID:
        if value is None:
            return UID(0)  # 约定 $objects[0]="$null"
        if isinstance(value, (str, bool, int, float)):
            key = (type(value), value)  # type 区分 bool 与 int（True == 1）
            ref = self._atom_refs.get(key)
            if ref is None:
                ref = self.new_object(value)
                self._atom_refs[key] = ref
            return ref
        if isinstance(value, (bytes, bytearray)):
            return self.new_object({
                "$class": self.class_ref("NSData", DATA_CLASS_CHAIN),
                "NS.data": bytes(value),
            })
        if isinstance(value, dict):
            # keyed archiver 的字典键必须是字符串（原键可能为 int，先统一转 str）
            items = [(str(key), item) for key, item in value.items()]
            return self.new_object({
                "$class": self.class_ref("NSDictionary", DICT_CLASS_CHAIN),
                "NS.keys": [self.reference(key) for key, _ in items],
                "NS.objects": [self.reference(item) for _, item in items],
            })
        if isinstance(value, (list, tuple)):
            return self.new_object({
                "$class": self.class_ref("NSArray", ARRAY_CLASS_CHAIN),
                "NS.objects": [self.reference(item) for item in value],
            })
        raise ValueError(f"不支持的归档类型：{type(value).__name__}")


def encode_keyed_object(fields: dict[str, object], class_name: str, class_chain: list[str] | None = None) -> bytes:
    """把 {键: 值} 编码为一个 keyed-archiver 类实例（encode_attachment 的通用底座）。"""
    archiver = _Archiver()
    chain = list(class_chain) if class_chain else [class_name, "NSObject"]
    root = archiver.new_object({
        "$class": archiver.class_ref(class_name, chain),
        **{str(key): archiver.reference(value) for key, value in fields.items()},
    })
    container = {
        "$version": ARCHIVER_VERSION,
        "$archiver": ARCHIVER_NAME,
        "$top": {"root": root},
        "$objects": archiver.objects,
    }
    return plistlib.dumps(container, fmt=plistlib.FMT_BINARY)


def encode_attachment(data: object, data_type: int = 0) -> bytes:
    """编码 LookinConnectionAttachment 请求载荷：{"0": data, "1": dataType}（请求侧 dataType 恒 0）。"""
    return encode_keyed_object(
        {"0": data, "1": data_type},
        class_name="LookinConnectionAttachment",
        class_chain=["LookinConnectionAttachment", "NSObject"],
    )


def unarchive(payload: bytes) -> tuple[object, list[str]]:
    """解码 NSKeyedArchiver binary plist，返回 (根对象, warnings)。"""
    try:
        container = plistlib.loads(payload)
    except (plistlib.InvalidFileException, ValueError) as error:
        raise CoreError("LOOKIN_UNAVAILABLE", f"载荷不是合法的 binary plist：{error}") from error
    if not isinstance(container, dict) or "$objects" not in container:
        raise CoreError("LOOKIN_UNAVAILABLE", "载荷不是 NSKeyedArchiver 归档结构（缺少 $objects）。")
    unarchiver = _Unarchiver(container)
    return unarchiver.root(), unarchiver.warnings


class _Unarchiver:
    """宽松展开 $top/$objects/$class 引用图。"""

    def __init__(self, container: dict[object, object]) -> None:
        self.container = container
        objects = container.get("$objects")
        self.objects: list[object] = objects if isinstance(objects, list) else []
        self.warnings: list[str] = []
        self._resolved: dict[int, object] = {}
        self._resolving: set[int] = set()

    def root(self) -> object:
        top = self.container.get("$top")
        root_ref = top.get("root") if isinstance(top, dict) else top
        if isinstance(root_ref, UID):
            return self.resolve(root_ref)
        return self.expand_entry(root_ref)

    def resolve(self, ref: UID) -> object:
        index = ref.data
        if not isinstance(index, int) or index < 0 or index >= len(self.objects):
            self.warnings.append(f"悬空引用：UID({index})")
            return None
        if index in self._resolved:
            return self._resolved[index]
        if index in self._resolving:
            self.warnings.append(f"循环引用：UID({index})")
            return None
        self._resolving.add(index)
        try:
            value = self.expand_entry(self.objects[index])
        finally:
            self._resolving.discard(index)
        self._resolved[index] = value
        return value

    def expand_entry(self, entry: object) -> object:
        if isinstance(entry, str) and entry == NULL_REF:
            return None
        if isinstance(entry, (str, bool, int, float, bytes)):
            return entry
        if isinstance(entry, UID):
            return self.resolve(entry)
        if isinstance(entry, list):
            return [self.expand_entry(item) for item in entry]
        if isinstance(entry, dict):
            if "$classname" in entry and "$classes" in entry:
                # 类骨架被当作值引用（罕见）：原样保留
                classes = entry.get("$classes")
                return {
                    "$classname": entry.get("$classname"),
                    "$classes": [str(name) for name in classes] if isinstance(classes, list) else [],
                }
            if "$class" in entry:
                return self.expand_instance(entry)
            return {str(key): self.expand_entry(value) for key, value in entry.items()}
        return entry

    def expand_instance(self, entry: dict[object, object]) -> object:
        chain = self.class_chain(entry.get("$class"))
        expanded: dict[str, object] = {}
        for key, value in entry.items():
            if key == "$class":
                continue
            expanded[str(key)] = self.expand_entry(value)
        lowered = [name.lower() for name in chain]
        if "nsdictionary" in lowered:
            keys = expanded.get("NS.keys")
            objects = expanded.get("NS.objects")
            if isinstance(keys, list) and isinstance(objects, list):
                return {str(key): value for key, value in zip(keys, objects)}
        elif "nsarray" in lowered:
            objects = expanded.get("NS.objects")
            if isinstance(objects, list):
                return objects
        elif "nsset" in lowered:  # NSCountedSet/NSMutableSet 的 $classes 链都含 NSSet
            objects = expanded.get("NS.objects")
            if isinstance(objects, list):
                return objects
        elif "nsstring" in lowered:
            value = expanded.get("NS.string")
            if isinstance(value, str):
                return value
        elif "nsdata" in lowered:  # NSMutableData 的链含 NSData
            value = expanded.get("NS.data")
            if isinstance(value, bytes):
                return value
        elif "nsnumber" in lowered:
            number = self._number_from(expanded)
            if number is not None:
                return number
        elif "nserror" in lowered:
            return self.decode_error(expanded)
        # 未知类骨架：保留键值并附 _classes 记录类名链（Lookin 业务对象都走这里）
        result = dict(expanded)
        if chain:
            result["_classes"] = chain
        return result

    def class_chain(self, class_ref: object) -> list[str]:
        if not isinstance(class_ref, UID):
            return []
        index = class_ref.data
        if not isinstance(index, int) or index < 0 or index >= len(self.objects):
            return []
        skeleton = self.objects[index]
        if not isinstance(skeleton, dict) or "$classname" not in skeleton:
            return []
        classes = skeleton.get("$classes")
        if isinstance(classes, list) and classes:
            return [str(name) for name in classes]
        return [str(skeleton.get("$classname"))]

    @staticmethod
    def _number_from(expanded: dict[str, object]) -> object | None:
        for key in _NUMBER_VALUE_KEYS:
            if key not in expanded:
                continue
            value = expanded[key]
            if isinstance(value, (bool, int, float)):
                return value
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    try:
                        return float(value)
                    except ValueError:
                        return value
        return None

    @staticmethod
    def decode_error(expanded: dict[str, object]) -> dict[str, object]:
        """NSError → {__type, domain, code, userInfo, description}；键名不识别时保留宽松缺省。"""
        lowered = {str(key).lower(): value for key, value in expanded.items()}
        domain = _first_value(lowered, _ERROR_DOMAIN_KEYS)
        code = _first_value(lowered, _ERROR_CODE_KEYS)
        user_info = _first_value(lowered, _ERROR_USERINFO_KEYS)
        if not isinstance(user_info, dict):
            user_info = {}
        if isinstance(code, float) and code.is_integer():
            code = int(code)
        description = (
            user_info.get("NSLocalizedDescription")
            or user_info.get("NSLocalizedFailureReason")
            or f"{domain or 'UNKNOWN_DOMAIN'}({code})"
        )
        return {
            "__type": "NSError",
            "domain": str(domain) if domain is not None else "",
            "code": code if code is not None else 0,
            "userInfo": user_info,
            "description": str(description),
        }


def decode_rect(value: object) -> dict[str, float] | None:
    """CGRect 宽松解码（真机校准点）。

    兼容：dict（X/Y/Width/Height、NS.x/NS.y/NS.width/NS.height、origin/size 嵌套，键名不分大小写）
    或 4 元素数组 [x, y, w, h]。返回 {"x","y","width","height"}（float）；无法识别返回 None。
    """
    if isinstance(value, (list, tuple)) and len(value) == 4:
        numbers = _float_list(value)
        if numbers is not None:
            return dict(zip(("x", "y", "width", "height"), numbers))
        return None
    if not isinstance(value, dict):
        return None
    lowered = {str(key).lower(): item for key, item in value.items()}
    origin = lowered.get("origin") if isinstance(lowered.get("origin"), dict) else None
    size = lowered.get("size") if isinstance(lowered.get("size"), dict) else None
    x = _pick_number(lowered, ("x", "ns.x"))
    y = _pick_number(lowered, ("y", "ns.y"))
    width = _pick_number(lowered, ("width", "ns.width"))
    height = _pick_number(lowered, ("height", "ns.height"))
    if x is None and origin is not None:
        x = _pick_number(origin, ("x",))
    if y is None and origin is not None:
        y = _pick_number(origin, ("y",))
    if width is None and size is not None:
        width = _pick_number(size, ("width",))
    if height is None and size is not None:
        height = _pick_number(size, ("height",))
    if x is None or y is None or width is None or height is None:
        return None
    return {"x": x, "y": y, "width": width, "height": height}


def _float_list(value: list[object] | tuple[object, ...]) -> list[float] | None:
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        numbers.append(float(item))
    return numbers


def _pick_number(source: dict[object, object], names: tuple[str, ...]) -> float | None:
    lowered = {str(key).lower(): item for key, item in source.items()}
    for name in names:
        if name not in lowered:
            continue
        value = lowered[name]
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


def _first_value(lowered: dict[str, object], names: tuple[str, ...]) -> object | None:
    for name in names:
        if name in lowered:
            return lowered[name]
    return None
