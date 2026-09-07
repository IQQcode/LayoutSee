# Uiautodev Desktop MCP 实时采集

## 状态

该链路已在真实 Android 设备验证，但尚未封装为 `parse_layout.py` 的输入参数。由主 Agent 调用当前会话可见的 MCP 工具获取 XML，再按 uiautomator XML 规则分析。

## 能力探测

1. 检查当前会话是否存在 Uiautodev Android MCP server。
2. server 名称可能包含设备 serial，不得长期硬编码。
3. 读取当前 server 的实际工具列表，只调用已暴露的工具。

常见工具：

- `get_device_info`
- `get_window_size`
- `dump_xml`
- `find_elements_by_xpath`
- `screenshot`
- `tap`、`swipe`、`press_key`、`input_text`

## 标准采集顺序

1. 调用 `get_device_info`，记录型号、serial 和连接状态。
2. 调用 `get_window_size`，记录屏幕宽高。
3. 调用 `dump_xml`，获取当前页面 uiautomator XML。
4. 记录采集时间，并把设备上下文与 XML 作为同一 PageState。
5. 需要精确查询时调用 `find_elements_by_xpath`，或在 XML 中按属性查询。
6. 需要视觉确认时再调用 `screenshot`。

## 页面一致性

MCP 不一定直接提供 current Activity。可结合 XML 中业务 package、页面标题、关键 resource-id 和其他可用设备接口判断页面。

若采集过程中执行了 tap、swipe、press_key 或 input_text，必须重新调用 `dump_xml`，不能继续使用交互前的布局树。

## 失败处理

- server 不存在：改用浏览器 HTTP、本地 XML 或 `.liv2`。
- 设备信息失败：停止实时分析，不复用旧设备上下文。
- `dump_xml` 失败或为空：重试一次，仍失败则报告采集失败。
- XPath 无结果：回到完整 XML 检查 resource-id、文本、父链路和 bounds。
- 自绘或 WebView 内容缺失：补充截图和视觉分析，并标记为推断。

## 输出要求

说明 MCP server、设备、屏幕尺寸、采集时间、页面证据和 XML 限制。聊天消息、账号、手机号等敏感文本只保留分析所需摘要。
