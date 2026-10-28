"""金样 fixture 一次性生成脚本（手工构造 keyed-archiver 图，不经自研 encoder，防编解码同源漂移）。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
运行方式（仓库根或任意目录）：

    python3 repos/core/tests/fixtures/lookin/make_fixture.py

产出：同目录 response_attachment_hierarchy.plist——LookinConnectionResponseAttachment
（lookinServerVersion=7、error=nil、dataTotalCount/currentDataCount=1、appIsInBackground=False）
包裹 LookinHierarchyInfo → UIWindow(frame 390x844, representedAsKeyWindow=True) →
UILabel(frame 20/100/200/44, text 属性 "你好，世界") 的 displayItems 树。
生成是确定性的：重复运行产物字节一致（可用 git diff 验证）。
"""
from __future__ import annotations

import plistlib
from pathlib import Path
from plistlib import UID

OUTPUT = Path(__file__).resolve().parent / "response_attachment_hierarchy.plist"


def main() -> None:
    objects: list[object] = []

    def add(entry: object) -> UID:
        objects.append(entry)
        return UID(len(objects) - 1)

    NULL = UID(0)  # $objects[0] = "$null"，nil 引用约定
    objects.append("$null")

    # 类骨架（手写，模拟 Apple archiver 输出布局）
    cls_response = add({"$classname": "LookinConnectionResponseAttachment", "$classes": ["LookinConnectionResponseAttachment", "NSObject"]})
    cls_hierarchy = add({"$classname": "LookinHierarchyInfo", "$classes": ["LookinHierarchyInfo", "NSObject"]})
    cls_array = add({"$classname": "NSArray", "$classes": ["NSArray", "NSObject"]})
    cls_dict = add({"$classname": "NSDictionary", "$classes": ["NSDictionary", "NSObject"]})
    cls_item = add({"$classname": "LookinDisplayItem", "$classes": ["LookinDisplayItem", "NSObject"]})
    cls_object = add({"$classname": "LookinObject", "$classes": ["LookinObject", "NSObject"]})
    cls_group = add({"$classname": "LookinAttributesGroup", "$classes": ["LookinAttributesGroup", "NSObject"]})
    cls_section = add({"$classname": "LookinAttributesSection", "$classes": ["LookinAttributesSection", "NSObject"]})
    cls_attr = add({"$classname": "LookinAttribute", "$classes": ["LookinAttribute", "NSObject"]})

    def atom(value: object) -> UID:
        return add(value)

    def array(items: list[UID]) -> UID:
        return add({"$class": cls_array, "NS.objects": list(items)})

    def dict_obj(pairs: list[tuple[str, object]]) -> UID:
        return add({"$class": cls_dict, "NS.keys": [add(key) for key, _ in pairs], "NS.objects": [add(value) for _, value in pairs]})

    def frame(x: float, y: float, w: float, h: float) -> UID:
        return dict_obj([("X", float(x)), ("Y", float(y)), ("Width", float(w)), ("Height", float(h))])

    # 业务对象图：窗口 → UILabel（带 text 属性组）
    # 键形态按 2026-10-26 实弹校准：HierarchyInfo 数字键（1=displayItems 2=appInfo），
    # section 内属性数组的键是 "attributes"，attr.identifier 是短码（lb_t_t=UILabel text）
    window_obj = add({"$class": cls_object, "oid": atom(1), "classChainList": array([atom("UIWindow"), atom("UIView")])})
    label_obj = add({"$class": cls_object, "oid": atom(2), "classChainList": array([atom("UILabel"), atom("UIView")])})
    attr = add({"$class": cls_attr, "identifier": atom("lb_t_t"), "attrType": atom(24), "value": atom("你好，世界"), "extraValue": NULL})
    section = add({"$class": cls_section, "identifier": atom("lb_t"), "attributes": array([attr])})
    group = add({"$class": cls_group, "identifier": atom("la"), "attrSections": array([section])})
    label = add({
        "$class": cls_item,
        "subitems": NULL,
        "frame": frame(20, 100, 200, 44),
        "bounds": NULL,
        "alpha": atom(1.0),
        "hidden": atom(False),
        "viewObject": label_obj,
        "layerObject": NULL,
        "attributesGroupList": array([group]),
        "backgroundColor": NULL,
        "representedAsKeyWindow": atom(False),
    })
    window = add({
        "$class": cls_item,
        "subitems": array([label]),
        "frame": frame(0, 0, 390, 844),
        "bounds": NULL,
        "alpha": atom(1.0),
        "hidden": atom(False),
        "viewObject": window_obj,
        "layerObject": NULL,
        "attributesGroupList": NULL,
        "backgroundColor": NULL,
        "representedAsKeyWindow": atom(True),
    })
    hierarchy = add({"$class": cls_hierarchy, "1": array([window]), "2": NULL, "serverVersion": atom(7)})
    attachment = add({
        "$class": cls_response,
        "0": hierarchy,
        "1": atom(0),
        "lookinServerVersion": atom(7),
        "error": NULL,
        "dataTotalCount": atom(1),
        "currentDataCount": atom(1),
        "appIsInBackground": atom(False),
    })

    container = {
        "$version": 100000,
        "$archiver": "NSKeyedArchiver",
        "$top": {"root": attachment},
        "$objects": objects,
    }
    OUTPUT.write_bytes(plistlib.dumps(container, fmt=plistlib.FMT_BINARY))
    print(f"written: {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
