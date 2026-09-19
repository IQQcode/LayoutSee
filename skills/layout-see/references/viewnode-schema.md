# LayoutSee 快照与节点 Schema

LayoutSee MCP `capture_layout` 与 `get_layout` 返回的结构，契约事实源在 `repos/contracts/schemas/snapshot/layout-snapshot.json`。字段以契约为准，本文供离线对照。

## 快照（get_layout 返回）

```json
{
  "snapshotId": "a1b2c3d4e5",
  "deviceId": "android-RFCY41B0EVZ",
  "createdAt": 1756272000000,
  "foreground": { "packageName": "com.baidu.tieba", "activity": "com.example.MainActivity" },
  "windowSizePx": { "width": 1080, "height": 2340 },
  "density": 3.0,
  "hierarchyAccuracy": "exact",
  "synchronization": "exact",
  "screenshot": { "width": 1080, "height": 2340, "contentUrl": "/api/v1/snapshots/.../png" },
  "roots": ["node-0"],
  "nodes": [],
  "warnings": []
}
```

- `hierarchyAccuracy`：`exact` / `best_effort` / `limited`。非 exact 时层级可信度下降。
- `synchronization`：`exact` / `best_effort` / `context_changed`。`context_changed` 表示抓取期间页面跳变，应重抓。
- `roots`：窗口根节点的 nodeKey 列表，多于一个通常意味着有弹窗或系统窗口叠加。

## 节点（LayoutNode）

```json
{
  "nodeKey": "node-42",
  "parentKey": "node-10",
  "depth": 3,
  "childIndex": 0,
  "className": "android.widget.TextView",
  "resourceId": "com.baidu.tieba:id/title",
  "text": "",
  "contentDescription": "",
  "boundsPx": { "left": 0, "top": 0, "right": 1080, "bottom": 120 },
  "boundsNormalized": { "left": 0, "top": 0, "right": 1, "bottom": 0.05 },
  "visible": true,
  "enabled": true,
  "clickable": false,
  "scrollable": false,
  "drawingOrder": 5,
  "raw": {}
}
```

必有字段：nodeKey、parentKey、depth、childIndex、className、boundsPx、boundsNormalized、visible、enabled、clickable、scrollable、raw。可选字段：resourceId、text、contentDescription、drawingOrder。

## 使用规则

- boundsPx 是绝对屏幕像素 `{left, top, right, bottom}`；width 为 right 减 left，height 为 bottom 减 top，center 由此计算。
- boundsNormalized 是 0 到 1 的归一化坐标，跨设备比例对比时用。
- 父子层级由 parentKey、depth、childIndex 显式给出，不靠 boundsPx 包含关系推断。
- nodeKey 仅在当前快照内稳定；跨快照比较优先用 resourceId、className、parentKey 链和 boundsPx。
- 相同 resourceId 必须结合 parentKey 链和 childIndex 消歧。
- raw 保留 Core 未归一化的原始属性，需要额外字段时查这里。

## 跨快照匹配

匹配优先级：

1. resourceId、className、parentKey 链一致。
2. text 或 contentDescription 一致。
3. boundsPx 接近。
4. childIndex 接近。

匹配不唯一时输出多个候选及置信度，不强行合并。
