# LayoutSee 快照与节点 Schema

LayoutSee MCP `capture_layout` 与 `get_layout` 返回的结构，契约事实源在 `repos/contracts/schemas/snapshot/layout-snapshot.json`。字段以契约为准，本文供离线对照。Android 与 iOS 快照同构，iOS 差异与示例见文末。

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
  "roots": ["0"],
  "nodes": [],
  "warnings": []
}
```

- `hierarchyAccuracy`：`exact` / `best_effort` / `limited`。非 exact 时层级可信度下降。
- `synchronization`：`exact` / `best_effort` / `context_changed`。`context_changed` 表示抓取期间页面跳变，应重抓。
- `roots`：窗口根节点的 nodeKey 列表，多于一个通常意味着有弹窗或系统窗口叠加。
- nodeKey 是层级路径（根为 `"0"`，子为 `"0.0"`、`"0.1"` 逐层下钻），仅在当前快照内稳定。

## 节点（LayoutNode）

```json
{
  "nodeKey": "0.1.2",
  "parentKey": "0.1",
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

必有字段：nodeKey、parentKey、depth、childIndex、className、boundsPx、boundsNormalized、visible、enabled、clickable、scrollable、raw。可选字段：resourceId、text、contentDescription、drawingOrder、extras。

## iOS 快照示例

iOS 快照与 Android 同构，差异集中在 foreground、density、className、resourceId 与 extras：

```json
{
  "snapshotId": "b2c3d4e5f6",
  "deviceId": "ios-sim-47164",
  "createdAt": 1761900000000,
  "foreground": { "packageName": "com.qmui.lookindemo", "appName": "LookinDemo" },
  "windowSizePx": { "width": 1170, "height": 2532 },
  "density": null,
  "hierarchyAccuracy": "best_effort",
  "synchronization": "best_effort",
  "screenshot": { "width": 1170, "height": 2532, "contentUrl": "/api/v1/snapshots/.../png" },
  "roots": ["0"],
  "nodes": [],
  "warnings": []
}
```

iOS 节点示例：

```json
{
  "nodeKey": "0.2.1",
  "parentKey": "0.2",
  "depth": 3,
  "childIndex": 0,
  "className": "UIButton",
  "resourceId": "",
  "text": "",
  "contentDescription": "",
  "boundsPx": { "left": 186, "top": 219, "right": 496, "bottom": 300 },
  "boundsNormalized": { "left": 0.158974, "top": 0.086493, "right": 0.423932, "bottom": 0.118483 },
  "visible": true,
  "enabled": true,
  "clickable": true,
  "scrollable": false,
  "extras": {
    "ivar": "_confirmButton",
    "groups": [
      {
        "identifier": "l",
        "sections": [
          {
            "identifier": "l_f",
            "attributes": [
              { "identifier": "l_f_f", "type": 20, "value": { "kind": "rect", "x": 62, "y": 73, "width": 103.3, "height": 27 } }
            ]
          }
        ]
      },
      {
        "identifier": "vl",
        "sections": [
          {
            "identifier": "v_i",
            "attributes": [
              { "identifier": "vl_i_i", "type": 0, "value": { "kind": "boolean", "value": true } }
            ]
          }
        ]
      }
    ]
  },
  "raw": {}
}
```

iOS 差异要点：

- `foreground.packageName` 为 bundleId（如 `com.qmui.lookindemo`），`appName` 为应用显示名，无 `activity`。
- `density` 恒为 null，iOS 无独立密度概念。
- `className` 是 ObjC 类名（`UIView`、`UIButton` 等）；自定义类（非 UI/NS/_/CA/CF 前缀）在 Web 端高亮。
- `resourceId` 恒为空：LookinServer 协议不含 accessibilityIdentifier，定位证据改用 extras 的 ivar 名、自定义类名与 text。
- `extras` 为 Lookin 属性分组：AttrGroup/AttrSection/AttrItem 三层，`identifier` 是 Lookin 短码（示例取常用值，完整映射见 web 端 `attrFormat.js` 与 LookinServer 的 LookinAttrIdentifiers.m）；值统一为 kind 结构（string/number/boolean/enum/color/point/size/rect/edges/chain/nil/raw）。`ivar` 名来自 ivarTraces，是宿主哪个 ivar 引用了本视图；属性分组采集有 600 节点上限，超限节点可能没有 extras。
- 快照内部 `item.frame` 相对父视图（示例 frame 的 x=62、y=73 为点坐标），Core 输出的 `boundsPx` 已沿父链累加并乘 scale 换算为窗口绝对像素，与 Android 同语义。
- 底图优先 203 拉的 key window 真实渲染图（真机/模拟器通用）；失败时模拟器回退 simctl 全屏截图、真机降级线框（仅真机线框降级时 `screenshot` 为 null，`get_screenshot` 报 `MEDIA_UNAVAILABLE`）。

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

匹配不唯一时输出多个候选及置信度，不强行合并。iOS 无 resourceId，第 1 条改用 ivar 名（extras）、自定义类名与 parentKey 链。
