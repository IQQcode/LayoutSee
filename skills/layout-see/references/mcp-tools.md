# LayoutSee Core MCP 工具清单

LayoutSee Core 通过 MCP 暴露 12 个内置工具，实现以 `repos/core` 的 `mcp_catalog.py` 为准。本文是离线速查与直连时的对照表，运行期以 `tools/list` 实际返回为准。

## 端点与协议

- 每台已连设备一个端点：`http://127.0.0.1:<port>/mcp/android-<serial>/{sse|message}`。
- 端口默认 11663，被占用时向后探测到 11672。
- device_id 恒为 `android-<serial>`，serial 来自 `adb devices`（如 `RFCY41B0EVZ`、`emulator-5554`）。
- 协议是 JSON-RPC 2.0，method 有 `initialize`、`tools/list`、`tools/call`。
- `tools/call` 返回体：`result.content[0].text` 是一段 JSON 字符串，需二次解析才拿到工具真正的返回对象；`result.isError` 标识工具级错误。

## 工具表

必填参数标 `*`。省略 `snapshotId` 的读工具作用在最新快照。

| 工具 | 类型 | 入参 | 返回要点 |
|---|---|---|---|
| `get_device_info` | read | 无 | deviceId, platform, serial, model, status, readonly, windowSizePx, density, orientation |
| `get_current_app` | read | 无 | packageName, activity |
| `capture_layout` | read | 无 | snapshotId, windowSizePx, orientation, nodeCount, synchronization, foreground, warnings |
| `get_layout` | read | snapshotId? | 完整快照对象，见 viewnode-schema.md |
| `get_layout_summary` | read | snapshotId? | elements（带 ref）, omittedElements |
| `diagnose_layout` | read | snapshotId? | findings{type,severity,nodeKey,evidence,suggestion}, pluginFindings |
| `query_xpath` | read | expression*（≤512）, snapshotId? | nodeKeys, matchCount |
| `find_element` | read | query*（≤200）, snapshotId? | ref, matchCount, nodeKey |
| `get_screenshot` | read | snapshotId? | contentType, base64, bytes |
| `tap` | write | x 与 y，或 ref；durationMs?（0 至 2000） | action, x, y |
| `swipe` | write | fromX*, fromY*, toX*, toY*；durationMs?（0 至 5000，默认 300） | action 及各坐标 |
| `input_text` | write | text*（≤512） | action, chars |

## 六类诊断（diagnose_layout）

`overlap` 重叠，`occlusion` 遮挡，`out_of_bounds` 越界，`small_touch_target` 点击区域过小，`text_truncation` 文本截断，`invisible_interactive` 不可见但可交互。插件可追加 `pluginFindings`，总量截断在 50 条。

## 常见错误码

- `SNAPSHOT_STALE`：无可用快照，先调 `capture_layout`。
- `READ_ONLY_MODE`：设备只读，写操作被拦。
- `REF_NOT_FOUND`：ref 对应节点不存在，重新 `find_element` 或 `get_layout_summary` 取 ref。
- `INVALID_ARGUMENT`：参数缺失或非法（如 `tap` 既无 x/y 也无 ref）。
- `MEDIA_UNAVAILABLE`：截图不可用，可重试。

## tap 的 ref 用法

`find_element` 或 `get_layout_summary` 返回的短 ref 可直接传给 `tap`，Core 会取该节点 boundsPx 中心点执行点击，省去手工算坐标。
