from __future__ import annotations

import re

from .errors import CoreError

SAFE_MARGIN = 8.0
MIN_SCORE = 60.0


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def find_element(record: dict[str, object], query: str) -> dict[str, object]:
    """确定性词法与结构检索（spec §13）：返回唯一 ref 或 AMBIGUOUS_ELEMENT。"""
    if not isinstance(query, str) or not query.strip():
        raise CoreError("INVALID_ARGUMENT", "缺少查询文本。")
    normalized = _normalize(query)
    nodes = record["snapshot"]["nodes"]
    scored: list[tuple[float, int, dict[str, object]]] = []
    for index, node in enumerate(nodes):
        if not node["visible"] and not node["clickable"]:
            continue
        score = _score(normalized, node)
        if score <= 0:
            continue
        if node.get("clickable") or node.get("scrollable") or _is_editable(node):
            score += 6
        if node["visible"]:
            score += 3
        center = node["boundsNormalized"]
        if 0 <= float(center["left"]) + float(center["right"]) <= 2 and 0 <= float(center["top"]) + float(center["bottom"]) <= 2:
            score += 1
        scored.append((score, index, node))

    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored or scored[0][0] < MIN_SCORE:
        return {"found": False, "query": query, "candidates": []}
    top_score, _, top_node = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    candidates = [
        {
            "nodeKey": node["nodeKey"],
            "score": round(score, 1),
            "summary": {
                "className": node["className"],
                "text": node.get("text", ""),
                "resourceId": node.get("resourceId", ""),
                "clickable": node["clickable"],
            },
        }
        for score, _, node in scored[:5]
    ]
    if top_score - runner_up < SAFE_MARGIN and len(scored) > 1:
        raise CoreError(
            "AMBIGUOUS_ELEMENT",
            "存在多个接近匹配的元素，请缩小查询范围。",
            details={"candidates": candidates},
        )
    ref = record["refs"][top_node["nodeKey"]]
    return {
        "found": True,
        "query": query,
        "ref": ref,
        "score": round(top_score, 1),
        "summary": {
            "className": top_node["className"],
            "text": top_node.get("text", ""),
            "resourceId": top_node.get("resourceId", ""),
            "boundsNormalized": top_node["boundsNormalized"],
            "clickable": top_node["clickable"],
        },
    }


def _is_editable(node: dict[str, object]) -> bool:
    class_name = node["className"]
    return "EditText" in class_name or node.get("raw", {}).get("class", "") and "EditText" in str(node["raw"].get("class", ""))


def _score(normalized: str, node: dict[str, object]) -> float:
    score = 0.0
    text = _normalize(str(node.get("text", "")))
    description = _normalize(str(node.get("contentDescription", "")))
    resource_id = _normalize(str(node.get("resourceId", "")))
    class_name = _normalize(node["className"])

    if text:
        if text == normalized:
            score = max(score, 100.0)
        elif normalized in text:
            score = max(score, 75.0)
        else:
            overlap = _token_overlap(normalized, text)
            score = max(score, min(60.0, overlap * 20.0))
    if description:
        if description == normalized:
            score = max(score, 95.0)
        elif normalized in description:
            score = max(score, 70.0)
        else:
            score = max(score, min(55.0, _token_overlap(normalized, description) * 18.0))
    if resource_id:
        if resource_id == normalized:
            score = max(score, 90.0)
        elif resource_id.endswith(normalized) or normalized in resource_id:
            score = max(score, 80.0)
    if class_name and normalized in class_name:
        score = max(score, 40.0)
    return score


def _token_overlap(left: str, right: str) -> int:
    left_tokens = set(_chunks(left))
    right_tokens = set(_chunks(right))
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens)) if left_tokens and right_tokens else 0


def _chunks(value: str) -> list[str]:
    return [value[index:index + 2] for index in range(len(value) - 1)]
