from __future__ import annotations

import math
import re

ALGORITHM_VERSION = "1.0"
TARGET_BUDGET = 1000


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


def summarize(record: dict[str, object], snapshot_id: str) -> dict[str, object]:
    """确定性语义摘要：同一快照与参数字节级一致；可交互元素不因低分被裁剪。"""
    nodes = record["snapshot"]["nodes"]
    refs = record["refs"]
    by_key = {node["nodeKey"]: node for node in nodes}

    interactive_keys: list[str] = []
    semantic_keys: list[str] = []
    for node in nodes:
        key = node["nodeKey"]
        if node["visible"] and (node["clickable"] or node["scrollable"] or "EditText" in node["className"] or node["raw"].get("checkable") == "true"):
            interactive_keys.append(key)
        label = _label(node)
        if node["visible"] and label and key not in interactive_keys:
            semantic_keys.append(key)

    kept: set[str] = set(interactive_keys)
    for key in interactive_keys + semantic_keys:
        parent = by_key[key].get("parentKey")
        while parent:
            if parent in kept:
                break
            kept.add(parent)
            parent = by_key[parent].get("parentKey")

    ordered = [node for node in nodes if node["nodeKey"] in kept]
    lines: list[str] = []
    total_tokens = 0
    total_interactive = len(interactive_keys)
    included_interactive = 0
    included_text = 0
    omitted_interactive = 0
    omitted_text = 0

    budget_exhausted = False
    # 先输出可交互节点，再输出语义节点；超预算时裁剪后者并标记 partial。
    for phase, source_keys in ((1, interactive_keys), (2, semantic_keys)):
        for key in source_keys:
            if budget_exhausted:
                if phase == 1:
                    omitted_interactive += 1
                else:
                    omitted_text += 1
                continue
            node = by_key[key]
            ref = refs[key]
            bounds = node["boundsNormalized"]
            flags = []
            if not node["enabled"]:
                flags.append("disabled")
            if node["raw"].get("checked") == "true":
                flags.append("checked")
            if node["raw"].get("selected") == "true":
                flags.append("selected")
            role = _role(node)
            label = _label(node)
            position = f"({bounds['left']:.2f},{bounds['top']:.2f},{bounds['right']:.2f},{bounds['bottom']:.2f})"
            suffix = f" [{', '.join(flags)}]" if flags else ""
            line = f"[{ref}] {role} {label} {position}{suffix}".strip()
            tokens = _estimate_tokens(line)
            if total_tokens + tokens > TARGET_BUDGET and lines:
                budget_exhausted = True
                if phase == 1:
                    omitted_interactive += 1
                else:
                    omitted_text += 1
                continue
            lines.append(line)
            total_tokens += tokens
            if phase == 1:
                included_interactive += 1
            else:
                included_text += 1

    partial = budget_exhausted or omitted_interactive > 0
    text = "\n".join(lines)
    return {
        "snapshotId": snapshot_id,
        "text": text,
        "estimatedTokens": total_tokens,
        "partial": partial,
        "coverage": {
            "totalInteractive": total_interactive,
            "includedInteractive": included_interactive,
            "omittedInteractive": omitted_interactive,
            "totalSemanticText": len(semantic_keys),
            "includedSemanticText": included_text,
            "omittedSemanticText": omitted_text,
        },
        "algorithmVersion": ALGORITHM_VERSION,
    }
