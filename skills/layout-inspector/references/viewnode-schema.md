# ViewNode 与 PageState 设计

## 状态说明

这是规划中的统一数据模型，当前 `parse_layout.py` 尚未完整实现这些字段。使用时不得宣称已有标准化器。

## ViewNode

建议字段：

```json
{
  "nodeId": "N_00042",
  "sourceType": "uiautomator",
  "hierarchyAccuracy": "exact_xml",
  "className": "android.widget.TextView",
  "resourceId": "com.baidu.tieba:id/title",
  "text": "",
  "contentDescription": "",
  "bounds": [0, 0, 1080, 120],
  "width": 1080,
  "height": 120,
  "centerX": 540,
  "centerY": 60,
  "clickable": false,
  "scrollable": false,
  "enabled": true,
  "visible": true,
  "depth": 3,
  "indexInParent": 0,
  "parentId": "N_00010",
  "children": []
}
```

`hierarchyAccuracy` 建议值：

- `exact_xml`：来自 XML 父子关系。
- `exact_v2`：来自 `.liv2` 的 `meta:__child__N` 显式层级。
- `approximate`：`.liv2` 固定 key 兜底结果，根据坐标包含推断。
- `visual_inferred`：来自视觉分析，不得与结构节点混用。

## PageState

建议字段：

```json
{
  "pageId": "P_001",
  "timestamp": "2026-07-13T00:00:00+08:00",
  "sourceType": "uiautodev_http",
  "device": {
    "serial": "***",
    "model": "SM-S9310"
  },
  "packageName": "com.baidu.tieba",
  "activity": "example.Activity",
  "screen": {
    "width": 1080,
    "height": 2340
  },
  "inputMethodVisible": false,
  "hasDialog": false,
  "nodes": []
}
```

## 标准化规则

- bounds 始终采用绝对屏幕像素 `[left, top, right, bottom]`。
- width、height、center 由 bounds 计算。
- 空字符串与缺失值要区分，必要时保留原始属性。
- `visible-to-user` 映射到 visible。
- 节点 ID 仅在当前快照内稳定，跨快照比较优先使用 resource-id、父链路、class 和 bounds。
- 相同 resource-id 必须结合父链路和 index 消歧。
- sourceType 和 hierarchyAccuracy 必填，避免混淆权威结构与视觉推断。

## 跨快照匹配建议

匹配优先级：

1. resource-id、class、父链路一致。
2. text 或 content-desc 一致。
3. bounds 接近。
4. indexInParent 接近。

匹配不唯一时输出多个候选及置信度，不强行合并。
