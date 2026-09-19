# LayoutSee 运行时视图感知工作流

## 核心原则

1. 运行时 View 树是结构证据，截图是视觉证据。
2. className、resourceId、boundsPx、父子关系和交互属性必须来自 `get_layout` 的结构源。
3. OCR、图标语义和业务含义属于补充或推断，不能冒充结构事实。
4. 修复前后使用同一采集源、同一页面状态和同一目标节点进行比较。

## 证据优先级

1. LayoutSee MCP `capture_layout` 加 `get_layout`：Core 归一化后的节点树，`parentKey` 给出精确层级，`boundsPx` 精确坐标，最权威。
2. `get_layout_summary`：语义摘要，快速定位骨架，元素带短 ref。
3. `diagnose_layout`：内置六类异常量化结论。
4. `get_screenshot`：视觉与语义补充，不能单独证明层级或 resource-id。

MCP 未连接时按 mcp-direct-fallback.md 脚本直连，数据同源，证据等级不变。

## 七阶段流程

### 1. 采集

`capture_layout` 抓取，随后 `get_device_info` 与 `get_current_app` 补设备与页面上下文。记录：数据源（MCP server 名或直连端点）、采集时间、设备 serial 与 model、packageName 与 activity、windowSizePx、snapshotId 与 synchronization。

`synchronization=context_changed` 表示抓取期间页面跳变，丢弃本批并重抓。

### 2. 标准化

Core 已归一化，直接使用：

- `boundsPx = {left, top, right, bottom}`，width 为 right 减 left，height 为 bottom 减 top，center 由 boundsPx 计算。
- `boundsNormalized` 为归一化坐标。
- 空 resourceId、text、contentDescription 即空字符串。
- 布尔属性 visible、enabled、clickable、scrollable 取 true 或 false。
- 层级看 `parentKey`、`depth`、`childIndex`；精度看 `hierarchyAccuracy`。

### 3. 查询

用 `find_element`（text、描述、resource-id）或 `query_xpath`（结构表达式）定位，也可在 `get_layout` 节点树里按属性筛。可用维度：resourceId、className、text、contentDescription、boundsPx、clickable、scrollable、enabled、visible、父子兄弟。

相同 resourceId 多次出现时，结合 parentKey 链、childIndex、text 和 boundsPx 消歧。

### 4. 解释

解释目标节点时包含：位于屏幕哪个区域、尺寸和点击中心点、父容器职责、关键兄弟节点、是否在列表或弹窗或标题栏或输入区或导航区、可能的业务职责（明确标为推断）。

### 5. 诊断

先跑 `diagnose_layout` 拿六类量化结论，再按需人工复核。详细规则见 [diagnosis-playbook.md](diagnosis-playbook.md)。

### 6. 源码关联

按 resourceId、自定义 View className、Activity 或 Fragment、可见文案、父容器与业务模块名称搜索 owner。输出候选、命中证据和置信度。没有唯一证据时不宣称已确定 owner。

### 7. 验证

写操作或修复后重新 `capture_layout`，比较：目标节点是否存在、boundsPx 与 width 与 height 与 center 是否变化、parentKey 链是否变化、clickable 与 enabled 与 visible 是否变化、是否新增遮挡节点、页面与键盘状态是否一致。最后用 `get_screenshot` 确认视觉，但截图不替代结构对比。

## 输出模板

```text
页面：<packageName / activity / 标题>
数据源：<MCP server 名 或 直连端点>，snapshotId=<id>
采集时间：<timestamp>

目标节点：
className：...
resourceId：...
boundsPx：...
尺寸：...
交互属性：...

结构关系：
父链路（parentKey）：...
关键兄弟：...

结论：
结构事实：...
视觉事实：...
推断：...
限制：...
```
