from __future__ import annotations

from .errors import CoreError
from .xpath import _evaluate


def _xpath_string(value: str) -> str:
    escaped = value.replace("'", "&apos;")
    return f"'{escaped}'"


def _match_count(expression: str, record: dict[str, object]) -> int:
    elements = record["elements"]
    if not elements:
        return 0
    return len(_evaluate(expression, elements[0], record["element_to_key"]))


def generate_selectors(record: dict[str, object], node_key: str) -> dict[str, object]:
    """按 spec §11.2 顺序生成候选选择器，每个候选在同一快照上重新执行。"""
    nodes = record["snapshot"]["nodes"]
    index = next((index for index, node in enumerate(nodes) if node["nodeKey"] == node_key), None)
    if index is None:
        raise CoreError("REF_NOT_FOUND", "节点不存在于当前快照，请重新抓取。", details={"nodeKey": node_key})
    node = nodes[index]
    class_name = node["className"]
    candidates: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    # kind 是机器可读的维度标记，前端「XPath by id/text/class」按它取用，不解析中文 reason
    def add(kind: str, expression: str, reason: str) -> None:
        if expression not in seen and len(candidates) < 8:
            seen.add(expression)
            candidates.append((kind, expression, reason))

    resource_id = node.get("resourceId")
    text = node.get("text")
    description = node.get("contentDescription")

    if resource_id:
        add("id", f"//*[@resource-id={_xpath_string(str(resource_id))}]", "完整 resource-id 唯一匹配")
    if text and text.strip():
        add("text", f"//{class_name}[@text={_xpath_string(text)}]", "text + className 组合匹配")
    if description and description.strip():
        add("desc", f"//{class_name}[@content-desc={_xpath_string(description)}]", "contentDescription + className 组合匹配")

    ancestor_id = _nearest_ancestor_resource_id(nodes, node)
    if ancestor_id:
        conditions = []
        if text and text.strip():
            conditions.append(f"@text={_xpath_string(text)}")
        if description and description.strip():
            conditions.append(f"@content-desc={_xpath_string(description)}")
        condition = " and ".join(conditions) if conditions else f"@class={_xpath_string(class_name)}"
        add("ancestor", f"//*[@resource-id={_xpath_string(ancestor_id)}]//{class_name}[{condition}]", "最近唯一 id 祖先 + 后代属性")

    sibling_index = 1 + sum(1 for other in nodes if other["nodeKey"] != node_key and other["className"] == class_name and other["childIndex"] < index)
    add("class", f"(//{class_name})[{sibling_index}]", "className + 同级序号最短路径")

    selectors = []
    for kind, expression, reason in candidates[:8]:
        count = _match_count(expression, record)
        if count < 1:
            continue
        selectors.append({
            "expression": expression,
            "matchCount": count,
            "stable": count == 1,
            "reason": reason,
            "kind": kind,
        })
        if len(selectors) >= 5:
            break
    return {"nodeKey": node_key, "selectors": selectors}


def _nearest_ancestor_resource_id(nodes: list[dict[str, object]], node: dict[str, object]) -> str | None:
    by_key = {item["nodeKey"]: item for item in nodes}
    parent_key = node.get("parentKey")
    while parent_key:
        parent = by_key.get(parent_key)
        if parent is None:
            break
        if parent.get("resourceId"):
            return str(parent["resourceId"])
        parent_key = parent.get("parentKey")
    return None
