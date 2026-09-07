---
name: layout-inspector
description: >
  面向 Agent 的 Android 运行时视图感知工作流。
  读取真实 View 树，分析页面结构、控件坐标、尺寸、
  resource-id、父子关系、点击区域、遮挡、重叠、弹窗层级、列表复用和键盘状态。支持已实现的
  .liv2 与 uiautomator XML 文件解析，也指导使用 Uiautodev Desktop MCP 和浏览器本地 HTTP 服务
  实时读取设备布局。用户提到布局快照、View 树、控件多大或在哪、点击区域、元素重叠、运行时层级、
  当前设备页面结构、uiautodev、hierarchy XML、Layout Inspector dump 时使用。不适用于静态 layout XML
  源码阅读或 iOS 视图调试。
---

# Layout Inspector

从 Android 运行时真实 View 树获取结构证据。默认原则是：**View 树证明结构，截图确认视觉，推断必须单独标注。**

## 触发条件

| 场景 | 行为 |
| --- | --- |
| 用户提供 `.liv2` 文件路径 | 读取 CHECK.md 检查插件来源，再调用 `parse_layout.py` 解析 |
| 用户提供 uiautomator XML 文件路径 | 直接调用 `parse_layout.py` 解析 |
| 用户提到布局快照、View 树、控件坐标、resource-id | 按七阶段工作流输出结构分析 |
| 用户询问控件大小、位置、点击区域、重叠、遮挡 | 解析当前可用的结构源，按诊断模板输出 |
| 用户需要当前设备页面结构 | 优先 Uiautodev Desktop MCP，其次浏览器 HTTP，最后截图推断 |
| 用户提到 uiautodev、hierarchy XML、Layout Inspector dump | 直接使用对应数据源 |
| 用户分析静态 layout XML 源码或 iOS 视图 | 不触发（超出能力范围） |
| 用户提到运行时层级、弹窗层级、列表复用、键盘状态 | 解析结构源并输出诊断结论 |


## 核心能力

- 解析 LayoutInspectorV2-Pro 导出的 `.liv2`（V2 协议，字符串表 + 嵌套 View Map，精确层级）。
- 解析失败时自动降级为固定 key 扫描器，标注近似层级和失败原因。
- 解析 uiautomator dump 的 hierarchy XML，完整保留文本和交互属性。
- 输出可读控件树和 JSON，支持 `--filter`、`--max-depth`、`--json`、`--json-only`。
- 通过 Uiautodev Desktop MCP 或浏览器 HTTP 实时读取设备布局。
- 七阶段工作流：采集 → 标准化 → 查询 → 解释 → 诊断 → 源码关联 → 验证。

## 使用方法

```bash
python3 .comate/skills/layout-inspector/scripts/parse_layout.py <文件路径> \
    [--json 输出.json] [--filter 关键字] [--max-depth N] [--json-only]
```

参数：

- `<文件路径>`：必填，`.liv2` 或 uiautomator XML。
- `--json`：将 JSON 写入指定路径。
- `--filter`：按 class 或 resource-id 过滤文本树。
- `--max-depth`：限制文本树深度。
- `--json-only`：只输出 JSON 到标准输出。

`bounds` 统一为 `[left, top, right, bottom]`，宽度为 `right - left`，高度为 `bottom - top`。

`.liv2` 的 JSON 结果包含解析精度元数据：

- `parser=v2-structured`、`hierarchy=exact`：已按 V2 嵌套 Map 恢复层级。
- `parser=legacy-key-scan`、`hierarchy=approximate`：完整解析失败，已使用旧扫描器兜底；必须同时查看 `warning`。

处理 `.liv2` 前必须读取 [CHECK.md](CHECK.md)。只解析 XML 时跳过插件检查。

## 七阶段工作流

完整协议见 [runtime-view-workflow.md](references/runtime-view-workflow.md)。执行顺序：

1. 采集：选择当前可用且权威程度最高的结构源，记录设备、页面、时间和来源。
2. 标准化：统一 bounds 和节点属性语义，保留原始标识。
3. 查询：按 resource-id、class、text、content-desc、bounds 和交互属性定位节点。
4. 解释：描述位置、尺寸、父子关系、兄弟关系和可能职责。
5. 诊断：检查重叠、遮挡、点击区域、列表复用、弹窗层级和键盘状态。
6. 源码关联：用 resource-id、class、Activity 和文案寻找 owner，输出候选和证据。
7. 验证：使用同一采集源重新抓取，对比修复前后结构，再以截图确认视觉。

## 分析输出要求

每次分析至少给出：

- 页面判断，以及 package、Activity、标题或关键节点证据。
- 数据源和采集时间。
- 目标节点的 class、resource-id、bounds、width、height。
- 父链路和关键兄弟节点。
- clickable、scrollable、enabled、visible-to-user 等属性。
- 结构事实、视觉事实和推断结论的明确区分。
- 自绘内容、WebView、节点缺失和数据源精度限制。

禁止只输出“看起来重叠”“大概在底部”等无结构证据结论。

## 精度与边界

- 完整解析的 V2 `.liv2` 使用 `meta:__child__N` 恢复父子层级；坐标根据父节点原点、滚动量和节点位置计算。
- 只有 `legacy-key-scan` 兜底结果使用 bounds 包含关系推断层级，此时父链和兄弟关系只能视为近似。
- 当前脚本不支持 V1 hierarchy。V1 文件会尝试旧扫描器兜底，无法识别时明确报错。
- uiautomator XML 保留 XML 父子关系和文本属性，但不能稳定覆盖所有自绘内容与 WebView 内部节点。
- MCP server 名称与当前设备和 Desktop.app 状态有关，必须使用当前会话实际发现的 server。
- 浏览器 HTTP 服务默认地址为 `127.0.0.1:20242`，设备 serial 必须每次动态获取。
- currentApp 与 hierarchy 应属于同一采集批次，采集期间页面变化时重新抓取。
- 截图不能单独证明 View 层级或 resource-id。

## 数据安全

- 只采集当前分析所需的最小数据。
- 非必要不复述完整聊天消息、账号、手机号和个人信息。
- 保存 hierarchy、JSON 或截图前明确输出路径。
- 示例和报告中的敏感文本、账号、手机号和设备标识按场景脱敏。

## 按需引用

- 完整工作流与证据分级：[runtime-view-workflow.md](references/runtime-view-workflow.md)
- Uiautodev Desktop MCP：[uiautodev-mcp.md](references/uiautodev-mcp.md)
- uiautodev 浏览器 HTTP：[uiautodev-browser-http.md](references/uiautodev-browser-http.md)
- ViewNode 与 PageState 设计：[viewnode-schema.md](references/viewnode-schema.md)
- 布局诊断模板：[diagnosis-playbook.md](references/diagnosis-playbook.md)
- `.liv2` 格式与限制：[liv2-format.md](references/liv2-format.md)
