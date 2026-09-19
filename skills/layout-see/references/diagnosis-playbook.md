# LayoutSee 布局诊断模板

`diagnose_layout` 已内置六类量化诊断（`overlap`、`occlusion`、`out_of_bounds`、`small_touch_target`、`text_truncation`、`invisible_interactive`），返回 `findings` 数组，每条含 `type`、`severity`、`nodeKey`、`evidence`、`suggestion`。本模板用于解读这些结论、人工复核，以及 diagnose 未覆盖的场景。所有判断基于 `get_layout` 的 `boundsPx` 与 `parentKey`。

## 重叠与遮挡（overlap / occlusion）

证据：

- 两个节点 boundsPx 相交。
- 上层节点（drawingOrder 或 childIndex 更靠后）覆盖目标节点区域。
- 覆盖节点可能透明，但占据相同坐标。
- 目标节点 visible=true 不代表没有被兄弟节点遮挡。

输出重叠矩形、覆盖比例、节点层级和 clickable 属性。

## 点击区域异常（small_touch_target）

检查：

- 目标节点自身 clickable。
- clickable 是否落在父容器（沿 parentKey 链上溯）。
- 父容器 boundsPx 是否明显大于视觉元素。
- 透明节点是否 clickable。
- 多个可点击节点是否区域重叠。

不能只根据图标 boundsPx 判断实际点击区域。

## 越界与裁剪（out_of_bounds）

检查：

- 子节点 boundsPx 是否超出父节点 boundsPx。
- 是否存在 clipChildren、translation 或动画导致的视觉偏移。
- `hierarchyAccuracy` 非 exact 时，层级与坐标可信度下降，结论需标注。

## 文本截断（text_truncation）

检查：

- 文本节点 boundsPx 宽高是否不足以容纳 text。
- 是否被兄弟节点挤压或父容器裁剪。
- 结合 `get_screenshot` 视觉确认，标为视觉推断。

## 不可见可交互（invisible_interactive）

检查：

- 节点 clickable=true 但 visible=false，或 boundsPx 为零面积。
- 是否残留在屏幕外仍可被点击命中。

## RecyclerView 与列表复用

检查：

- 相同 resourceId 是否出现在多个 item。
- item boundsPx 是否重复、重叠或残留在屏幕外。
- visible、enabled 等状态是否与当前位置一致。
- 诊断结论结合 item 的 parentKey 链和 childIndex 证据。

## 弹窗与蒙层

检查：

- 节点树是否包含多个窗口根（roots 多于一个）或多个 package。
- 蒙层是否覆盖业务窗口。
- 弹窗外区域是否 clickable。
- 系统窗口、侧屏面板、输入法和业务弹窗分开描述。

## 键盘与输入区

证据：

- 输入区底部 boundsPx 是否接近屏幕底部。
- 页面可用高度（windowSizePx）是否缩小。
- 输入法 package 或窗口节点是否出现。
- 输入区是否整体上移。

结构证据不足时才用 `get_screenshot` 判断键盘状态，并标为视觉推断。

## WebView 与自绘内容

`get_layout` 可能只返回 WebView 容器，忽略 Canvas 内部元素。此时：

1. 先说明 View 树能力边界。
2. 用 `get_screenshot` 或浏览器 CDP、OCR 补充语义。
3. 不为视觉元素虚构 resourceId 或原生父链路。

## 结论分层

```text
结构事实：直接来自 View 树（get_layout）。
视觉事实：直接来自截图（get_screenshot）。
推断：结合结构、视觉和业务知识得出的解释。
限制：数据源无法覆盖的内容。
```
