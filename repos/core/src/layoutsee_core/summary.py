from __future__ import annotations

import math
import re

ALGORITHM_VERSION = "1.1"
DEFAULT_MAX_TOKENS = 1200


def _role(node: dict[str, object]) -> str:
    class_name = node["className"]
    if "EditText" in class_name:
        return "输入框"
    if "Button" in class_name or node["clickable"]:
        return "按钮"
    if "ImageView" in class_name:
        return "图片"
    if "RecyclerView" in class_name or "ListView" in class_name or "ScrollView" in class_name:
        return "列表"
    if "CheckBox" in class_name or "RadioButton" in class_name or "Switch" in class_name:
        return "开关"
    if "TextView" in class_name:
        return "文本"
    return class_name.rsplit(".", 1)[-1]


def _label(node: dict[str, object]) -> str:
    for key in ("text", "contentDescription", "resourceId"):
        value = str(node.get(key, "")).strip()
        if value:
            return value if len(value) <= 120 else value[:117] + "…"
    return ""


def _estimate_tokens(text: str) -> int:
    """保守估算：CJK 每字 1，ASCII 连续词 ceil(len/4)，标点单独计。"""
    cjk = len(re.findall(r"[\u3000-\u9fff\uff00-\uffef\u4e00-\u9fa5]", text))
    ascii_words = re.findall(r"[A-Za-z0-9_./:]+", text)
    word_tokens = sum(max(1, math.ceil(len(word) / 4)) for word in ascii_words)
    punctuation = len(re.findall(r"[^\w\u3000-\u9fff\uff00-\uffef\u4e00-\u9fa5]", text))
    return cjk + word_tokens + punctuation


def _is_interactive(node: dict[str, object]) -> bool:
    return bool(node["visible"]) and (
        node["clickable"]
        or node["scrollable"]
        or "EditText" in node["className"]
        or node["raw"].get("checkable") == "true"
    )


def _format_line(node: dict[str, object], ref: str) -> str:
    bounds = node["boundsNormalized"]
    flags = []
    if not node["enabled"]:
        flags.append("disabled")
    if node["raw"].get("checked") == "true":
        flags.append("checked")
    if node["raw"].get("selected") == "true":
        flags.append("selected")
    position = f"({bounds['left']:.2f},{bounds['top']:.2f},{bounds['right']:.2f},{bounds['bottom']:.2f})"
    suffix = f" [{', '.join(flags)}]" if flags else ""
    return f"[{ref}] {_role(node)} {_label(node)} {position}{suffix}".strip()


def summarize(record: dict[str, object], snapshot_id: str, *, max_tokens: int | None = DEFAULT_MAX_TOKENS) -> dict[str, object]:
    """确定性语义摘要：可交互元素无条件保留，仅语义文本节点受预算裁剪。

    同一快照与同一 max_tokens 的输出字节级一致；生成异常时降级为最简可交互清单。
    """
    try:
        budget = int(max_tokens)
    except (TypeError, ValueError):
        budget = DEFAULT_MAX_TOKENS
    if budget <= 0:
        budget = DEFAULT_MAX_TOKENS
    try:
        return _summarize(record, snapshot_id, budget)
    except Exception:
        return _degrade(record, snapshot_id, budget)


def _summarize(record: dict[str, object], snapshot_id: str, budget: int) -> dict[str, object]:
    nodes = record["snapshot"]["nodes"]
    refs = record["refs"]
    by_key = {node["nodeKey"]: node for node in nodes}

    interactive_keys = [node["nodeKey"] for node in nodes if _is_interactive(node)]
    interactive_set = set(interactive_keys)
    semantic_keys = [
        node["nodeKey"]
        for node in nodes
        if node["nodeKey"] not in interactive_set and node["visible"] and _label(node)
    ]

    lines: list[str] = []
    total_tokens = 0
    included_text = 0
    omitted_text = 0

    # 可交互节点无条件保留，不参与预算裁剪（PRD 底线：可交互元素必保留）
    for key in interactive_keys:
        line = _format_line(by_key[key], refs[key])
        total_tokens += _estimate_tokens(line)
        lines.append(line)
    interactive_tokens = total_tokens

    # 语义文本节点在剩余预算内纳入，超出即裁剪并标记 partial
    for key in semantic_keys:
        line = _format_line(by_key[key], refs[key])
        tokens = _estimate_tokens(line)
        if total_tokens + tokens > budget:
            omitted_text += 1
            continue
        lines.append(line)
        total_tokens += tokens
        included_text += 1

    text = "\n".join(lines)
    raw_chars = len(str(record.get("xml", "") or ""))
    summary_chars = len(text)
    return {
        "snapshotId": snapshot_id,
        "text": text,
        "estimatedTokens": total_tokens,
        "maxTokens": budget,
        "partial": omitted_text > 0,
        "degraded": False,
        "interactiveOverBudget": interactive_tokens > budget,
        "compressionRatio": {
            "rawChars": raw_chars,
            "summaryChars": summary_chars,
            "ratio": round(summary_chars / raw_chars, 4) if raw_chars else None,
        },
        "coverage": {
            "totalInteractive": len(interactive_keys),
            "includedInteractive": len(interactive_keys),
            "omittedInteractive": 0,
            "totalSemanticText": len(semantic_keys),
            "includedSemanticText": included_text,
            "omittedSemanticText": omitted_text,
        },
        "algorithmVersion": ALGORITHM_VERSION,
    }

# __APPEND__
