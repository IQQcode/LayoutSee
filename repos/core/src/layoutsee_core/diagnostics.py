from __future__ import annotations

import time
from typing import Callable

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
RULE_NAMES = {
    "overlap": "重叠",
    "occlusion": "遮挡",
    "out_of_bounds": "越界",
    "small_touch_target": "触控热区过小",
    "text_truncation": "文本截断",
    "invisible_interactive": "隐形可交互",
}


def diagnose(record: dict[str, object], snapshot_id: str) -> dict[str, object]:
    started = time.monotonic()
    nodes = record["snapshot"]["nodes"]
    snapshot = record["snapshot"]
    width = snapshot["windowSizePx"]["width"]
    height = snapshot["windowSizePx"]["height"]
    density = snapshot.get("density")
    by_key = {node["nodeKey"]: node for node in nodes}
    findings: list[dict[str, object]] = []
    counter = 0

    def add(
        finding_type: str,
        severity: str,
        node_keys: list[str],
        evidence_kind: str,
        confidence: str,
        metrics: dict[str, object],
        evidence: str,
        suggestion: str,
    ) -> None:
        nonlocal counter
        counter += 1
        findings.append({
            "findingId": f"{snapshot_id}-{counter}",
            "type": finding_type,
            "severity": severity,
            "nodeKeys": node_keys,
            "evidenceKind": evidence_kind,
            "confidence": confidence,
            "metrics": metrics,
            "evidence": evidence,
            "suggestion": suggestion,
        })

    interactive = [
        node for node in nodes
        if node["visible"] and (node["clickable"] or node["scrollable"] or "EditText" in node["className"])
    ]

    for node in nodes:
        bounds = node["boundsPx"]
        left, top, right, bottom = bounds["left"], bounds["top"], bounds["right"], bounds["bottom"]
        key = node["nodeKey"]
        area = (right - left) * (bottom - top)

        if node["visible"] and (left < -1 or top < -1 or right > width + 1 or bottom > height + 1):
            add("out_of_bounds", "error", [key], "structure", "high",
                {"left": left, "top": top, "right": right, "bottom": bottom, "width": width, "height": height},
                f"节点 {node['className']} 的 bounds 超出窗口 [{width}x{height}]。",
                "检查布局中是否存在固定超屏尺寸或动画中途的位移。")

        if node["clickable"] and node["enabled"] and (not node["visible"] or area <= 0 or left >= width or top >= height):
            add("invisible_interactive", "warning", [key], "structure", "high",
                {"area": area},
                f"节点 {node['className']} 声明可点击且启用，但不可见或完全离开屏幕。",
                "该元素无法被用户触达，建议移除 clickable 或修复其可见性。")

        if node["clickable"] and node["visible"] and area > 0:
            width_px = right - left
            height_px = bottom - top
            if density:
                min_dp = min(width_px, height_px) / (density / 160.0)
                if min_dp < 44:
                    add("small_touch_target", "warning", [key], "structure", "high",
                        {"widthPx": width_px, "heightPx": height_px, "minDp": round(min_dp, 1), "density": density},
                        f"可点击节点最小边仅 {min_dp:.1f}dp，低于 44dp 触控标准。",
                        "扩大点击区域或为相邻区域补充冗余热区。")
            else:
                if min(width_px, height_px) < 24:
                    add("small_touch_target", "info", [key], "structure", "low",
                        {"widthPx": width_px, "heightPx": height_px, "densityKnown": False},
                        f"可点击节点尺寸仅 {width_px}x{height_px}px，设备 density 未知，无法换算 dp。",
                        "建议在设备驱动可用后复核触控热区。")

        text = str(node.get("text", "") or "")
        if node["visible"] and (text.rstrip().endswith("…") or text.rstrip().endswith("...")):
            add("text_truncation", "info", [key], "inference", "medium",
                {"text": text[-40:]},
                f"文本疑似被省略：{text[-24:]}",
                "核对原始文案是否完整，必要时放宽行数或扩大容器。")

    _overlap_and_occlusion(interactive, by_key, add, density)
    _parent_clipped(interactive, by_key, add, width, height)

    findings.sort(key=lambda finding: (
        SEVERITY_ORDER.get(str(finding["severity"]), 9),
        str(finding["type"]),
        str(finding["nodeKeys"][0]) if finding["nodeKeys"] else "",
    ))
    return {
        "snapshotId": snapshot_id,
        "findings": findings,
        "rulesChecked": list(RULE_NAMES.keys()),
        "rulesSkipped": [],
        "nodesChecked": len(nodes),
        "elapsedMs": int((time.monotonic() - started) * 1000),
    }


def _overlap_and_occlusion(
    interactive: list[dict[str, object]],
    by_key: dict[str, dict[str, object]],
    add: Callable[..., None],
    density: int | None,
) -> None:
    pairs: set[tuple[str, str]] = set()
    for node in interactive:
        bounds = node["boundsPx"]
        left, top = bounds["left"], bounds["top"]
        right, bottom = bounds["right"], bounds["bottom"]
        for other in interactive:
            if other is node:
                continue
            pair = tuple(sorted((str(node["nodeKey"]), str(other["nodeKey"]))))
            if pair in pairs:
                continue
            other_bounds = other["boundsPx"]
            overlap_w = min(right, other_bounds["right"]) - max(left, other_bounds["left"])
            overlap_h = min(bottom, other_bounds["bottom"]) - max(top, other_bounds["top"])
            if overlap_w <= 0 or overlap_h <= 0:
                continue
            overlap_area = overlap_w * overlap_h
            area_a = max(1, (right - left) * (bottom - top))
            area_b = max(1, (other_bounds["right"] - other_bounds["left"]) * (other_bounds["bottom"] - other_bounds["top"]))
            ratio = overlap_area / min(area_a, area_b)
            if ratio < 0.3:
                continue
            if _is_ancestor(node, other, by_key) or _is_ancestor(other, node, by_key):
                continue
            pairs.add(pair)
            node_keys = [str(node["nodeKey"]), str(other["nodeKey"])]
            add("overlap", "warning", node_keys, "structure", "high",
                {"overlapRatio": round(ratio, 2)},
                f"{node['className']} 与 {other['className']} 相互重叠 {ratio:.0%}。",
                "检查两个可交互区域的堆叠关系，确认目标元素是否被意外覆盖。")
            later, earlier = (node, other) if int(node["drawingOrder"]) > int(other["drawingOrder"]) else (other, node)
            add("occlusion", "info", node_keys, "inference", "medium",
                {"overlapRatio": round(ratio, 2), "drawingOrderEarlier": earlier["drawingOrder"], "drawingOrderLater": later["drawingOrder"]},
                f"{later['className']} 按层级顺序绘制在 {earlier['className']} 之上，可能遮挡其可点击区域。",
                "无系统绘制顺序时结论为推断；建议在真机上确认触摸落点。")


def _is_ancestor(node: dict[str, object], candidate: dict[str, object], by_key: dict[str, dict[str, object]]) -> bool:
    parent = candidate.get("parentKey")
    while parent:
        if parent == node["nodeKey"]:
            return True
        parent = by_key.get(parent, {}).get("parentKey")
    return False


def _parent_clipped(
    interactive: list[dict[str, object]],
    by_key: dict[str, dict[str, object]],
    add: Callable[..., None],
    width: int,
    height: int,
) -> None:
    for node in interactive:
        parent = by_key.get(str(node.get("parentKey") or ""))
        if parent is None or not parent["visible"]:
            continue
        parent_bounds = parent["boundsPx"]
        node_bounds = node["boundsPx"]
        if parent_bounds["right"] <= width and parent_bounds["bottom"] <= height:
            continue
        if node_bounds["right"] > parent_bounds["right"] + 1 or node_bounds["bottom"] > parent_bounds["bottom"] + 1:
            add("out_of_bounds", "warning", [str(node["nodeKey"])], "structure", "medium",
                {"parentRight": parent_bounds["right"], "nodeRight": node_bounds["right"], "parentBottom": parent_bounds["bottom"], "nodeBottom": node_bounds["bottom"]},
                f"{node['className']} 超出父容器 {parent['className']} 的可裁剪边界。",
                "检查父容器尺寸与子元素布局参数，可能被父级裁剪。")
