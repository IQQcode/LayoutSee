---
name: layout-see
description: >
  通过 LayoutSee Core MCP 读取 Android 真机运行时 View 树并分析布局。定位控件坐标、
  尺寸、resource-id、父子层级，诊断重叠、遮挡、点击区域、越界、列表复用、弹窗层级和
  键盘状态。用户提到 LayoutSee、布局查看、视图树、控件在哪或多大、当前设备页面结构、
  capture_layout、get_layout、layoutsee-android MCP，或问某控件能不能点、为什么错位、
  被谁挡住时使用；MCP 未连接时按脚本直连本地端点兜底。不用于静态 layout XML 源码阅读
  或 iOS 视图调试。
---

# LayoutSee 布局查看

通过 LayoutSee Core MCP 从 Android 真机运行时 View 树获取结构证据。核心原则：**View 树证明结构，截图确认视觉，推断单独标注。**

## 触发条件

| 场景 | 行为 |
| --- | --- |
| 需要当前设备页面结构、视图树、控件树 | 按「数据源与自动适配」选源，采集后按七阶段输出 |
| 询问控件坐标、尺寸、resource-id、父子层级 | 采集快照，定位目标节点，给结构事实 |
| 询问点击区域、重叠、遮挡、越界、列表复用、弹窗层级、键盘状态 | 采集后调 `diagnose_layout`，按诊断模板输出 |
| 提到 LayoutSee、capture_layout、get_layout、layoutsee-android MCP | 直接走对应 MCP 工具 |
| 会话内有 layoutsee-android server 工具 | 首选 UseMcpTool 调用，不要跳过它先上脚本 |
| 探测确认 MCP 不可用（无 server、工具为空、UseMcpTool 报错）| 再走脚本直连兜底，见 mcp-direct-fallback.md |
| 分析静态 layout XML 源码或 iOS 视图 | 不触发，超出能力范围 |

## 数据源与自动适配 MCP

LayoutSee Core 是本地 HTTP 服务（默认 `127.0.0.1:11663`，端口被占时向后探测到 11672），对每台已连设备暴露一个 MCP 端点，路径为 `/mcp/android-<serial>/sse`。**优先走 MCP 工具，确认不可用再兜底**，两条通道能力完全一致：

1. 首选 MCP 工具：先探测会话内的 `layoutsee-android-<serial>` server（名字带设备 serial，随设备变化，用当前会话实际发现的名字，不要写死）。该 server 有可用工具时，一律用 UseMcpTool 调 `capture_layout` / `get_layout` 等，不要跳过它直接上脚本。
2. 判定 MCP 不可用：出现以下任一情况即视为通道不可用，转第 3 步。会话内没有 `layoutsee-android-*` server；加载该 server 后工具列表为空（多为未配置，或 Core 未按新协议连上）；UseMcpTool 报未连接或调用失败。
3. 兜底脚本直连：确认 MCP 不可用后，按 [mcp-direct-fallback.md](references/mcp-direct-fallback.md) 用 `scripts/mcp_call.py` 直连本地 message 端点，行为与 MCP 工具一致。
4. 两者都不可用：说明 Core 未运行或无设备，停止结构分析，不要用截图脑补层级。

## MCP 工具地图

12 个内置工具（读 9 写 3），完整入参、返回与错误码见 [mcp-tools.md](references/mcp-tools.md)。

读取类：

- `capture_layout`：原子抓取当前页面（冻结、dump、截图、建索引一次完成），返回 snapshotId、nodeCount、synchronization、foreground、warnings。
- `get_layout`：取指定快照的完整节点树与上下文，省略 snapshotId 时用最新快照。
- `get_layout_summary`：确定性语义摘要，元素带短 ref，适合先看页面骨架。
- `diagnose_layout`：六类布局异常诊断，返回量化证据与建议。
- `query_xpath`：在快照原始 XML 上执行 XPath，返回 nodeKey 列表。
- `find_element`：按 text、描述或 resource-id 检索，返回 ref 与 nodeKey。
- `get_device_info`：设备型号、serial、窗口尺寸、密度、朝向、只读状态。
- `get_current_app`：前台包名与 Activity。
- `get_screenshot`：当前或指定快照的 PNG 截图（base64），仅用于视觉确认。

写入类（走只读门禁与审计，见「写操作安全」）：`tap` 按坐标或 ref 点击，`swipe` 滑动手势，`input_text` 输入文本。

## 标准采集顺序

1. `capture_layout` 抓取当前页面，记录 snapshotId、foreground、synchronization。
2. `get_layout` 取完整节点树；只看页面骨架时用 `get_layout_summary`。
3. 定位目标：`find_element`（文案、描述、id）或 `query_xpath`（结构表达式）。
4. 查异常：`diagnose_layout`。
5. 记录设备、页面、采集时间、数据源，归为同一次 PageState。

`synchronization=context_changed` 表示抓取期间页面发生跳变，丢弃本次结果并重抓。执行 `tap`、`swipe`、`input_text` 后页面已变，必须重新 `capture_layout`，不能复用旧快照。

## 七阶段工作流

采集，标准化，查询，解释，诊断，源码关联，验证。完整协议与证据分级见 [runtime-view-workflow.md](references/runtime-view-workflow.md)。

## 分析输出要求

每次分析至少给出：

- 页面判断，以及 package、Activity、标题或关键节点证据。
- 数据源（MCP server 名或直连端点）和采集时间。
- 目标节点的 className、resourceId、boundsPx、width、height。
- 父链路（parentKey 链）和关键兄弟节点。
- clickable、scrollable、enabled、visible 等交互属性。
- 结构事实、视觉事实、推断结论的明确区分。
- 自绘内容、WebView、节点缺失和数据源精度限制。

不要只输出"看起来重叠""大概在底部"这类无结构证据的结论。

## 写操作安全

`tap`、`swipe`、`input_text` 会真实操作设备，Core 对写操作做只读门禁与审计。默认只做只读分析；仅在用户明确要求操作设备时调用写工具，操作后重新 `capture_layout` 验证效果。设备处于只读模式时写工具返回 `READ_ONLY_MODE`，此时不要绕过，向用户说明。

## 精度与边界

- `boundsPx` 是 `{left, top, right, bottom}` 绝对屏幕像素；width 为 right 减 left，height 为 bottom 减 top；另有归一化坐标 `boundsNormalized`。
- 父子层级由 `parentKey`、`depth`、`childIndex` 显式给出，不靠 bounds 包含关系推断。
- `hierarchyAccuracy` 取值 `exact`、`best_effort`、`limited`；非 exact 时层级可信度下降，需在结论中标注。
- 相同 resourceId 多次出现时，结合 parentKey 链、childIndex、text 和 bounds 消歧。
- WebView 与自绘 Canvas 的内部节点可能缺失，`get_layout` 覆盖不到时用 `get_screenshot` 视觉补充并标为推断。
- 截图不能单独证明 View 层级或 resource-id。
- MCP server 名和端口随设备与 Core 状态变化，每次动态确认，不写死。

## 数据安全

- 只采集当前分析所需的最小数据。
- 视图树可能含聊天消息、账号、手机号，非必要不复述完整原文。
- 保存快照 JSON 或截图前明确输出路径。
- 示例与报告中的敏感文本、账号、设备标识按场景脱敏。

## 按需引用

- MCP 工具清单与 JSON-RPC 协议：[mcp-tools.md](references/mcp-tools.md)
- MCP 未连接时脚本直连：[mcp-direct-fallback.md](references/mcp-direct-fallback.md)
- 七阶段工作流与证据分级：[runtime-view-workflow.md](references/runtime-view-workflow.md)
- 布局诊断模板：[diagnosis-playbook.md](references/diagnosis-playbook.md)
- 快照与节点 schema：[viewnode-schema.md](references/viewnode-schema.md)
