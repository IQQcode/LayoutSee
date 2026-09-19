# MCP SSE Transport 回推改造设计

## 背景与问题

LayoutSee Core 对每台设备暴露 MCP 端点 `/mcp/android-<serial>/{sse,message}`。当前是「半截 SSE」实现：

- `GET .../sse`（`repos/core/src/layoutsee_core/server.py:790` `_mcp_sse`）只推一条 `endpoint` 事件与 15 秒心跳，从不推 JSON-RPC 响应。
- `POST .../message`（`server.py:808` `_mcp_message`）把响应同步写在 POST 的 HTTP body（`server.py:847`）。

标准 MCP HTTP+SSE 传输要求：客户端 POST 请求后，服务器把 JSON-RPC 响应通过 SSE 长连接以 `event: message` 推回，POST 本身回 202。所以标准 MCP 客户端（Comate 等）POST 完 `initialize` 后一直在 SSE 通道等响应，永远等不到，握手挂起，表现为「会话内该 server 已连接但工具列表为空」。

脚本直连 `skills/layout-see/scripts/mcp_call.py` 能用，正因为它直接读 POST body，不走 SSE 等待。

实测证据：`curl -N .../sse` 只回 `event: endpoint`；`_mcp_sse` 之后是纯心跳死循环，从不写响应。

## 目标

1. 让标准 MCP SSE 客户端能完成 `initialize` / `tools/list` / `tools/call` 握手，会话内正常列出并调用工具。
2. 不破坏现有脚本直连兜底（POST body 同步返回）。
3. 线程安全，SSE 断连不泄漏资源。

非目标：不改 12 个工具本身；不引入 2025 版 streamable-http；不动端口与鉴权模型。

## 方案总览

以 `sessionId` 区分两种调用模式，二者共存：

- **标准 SSE 模式**：`GET .../sse` 时生成 sessionId，注册「sessionId 到发送队列」，`endpoint` 事件下发 `/mcp/<device>/message?sessionId=<sid>`。客户端 POST 带 sessionId，Core 把响应放进该 session 队列并回 202，SSE 线程从队列取出以 `event: message` 推回。
- **直连兜底模式**：POST 不带 sessionId 或 sessionId 已失效，Core 保持现状，把响应同步写在 POST body（200）。

## 详细设计

### SSE 会话注册表 McpSseHub

- 线程安全（`threading.Lock`）的 `dict[sessionId 到 _McpSession]`。
- `_McpSession`：sessionId、deviceId、一个有界 `queue.Queue`（maxsize 64）。
- `open(deviceId)` 生成 sessionId 并注册；`close(sessionId)` 移除；`get(sessionId)` 取出。
- 挂在 `LoopbackServer` 实例上（`server.mcp_hub`），所有 handler 线程共享。不侵入 `CoreContext` 与 `bootstrap`，改动内聚在 server.py。

### _mcp_sse（GET）

1. 校验设备存在后 `open` 一个 session，设 `close_connection = True`（长连接不复用，与 `_media_stream` 一致）。
2. 先写 `event: endpoint` 与 `data: /mcp/<device>/message?sessionId=<sid>`。
3. 循环 `queue.get(timeout=15)`：取到消息写 `event: message` 加 `data: <json>`；超时写 `: keep-alive` 心跳。
4. `finally` 里 `hub.close(sessionId)`，断连即清理。

### _mcp_message（POST）

1. 沿用现有逻辑解析 body 得到 JSON-RPC response（`initialize` / `tools/list` / `tools/call` / `ping`）。
2. `notifications/initialized` 无需响应，直接回 202。
3. 取 query 的 sessionId：
   - 命中活跃 session：response 入队（`put` 超时则退回 body），POST 回 202。
   - 无 sessionId 或未命中：`_json(200, response)`，即直连兜底。

### 协议

- `protocolVersion` 保持 `2024-11-05`（HTTP+SSE 传输）。
- `endpoint` 事件 data 由 `/mcp/<device>/message` 改为带 `?sessionId=<sid>` 的相对路径。

## 兼容性

- 直连脚本 `mcp_call.py` 不带 sessionId，走 body 返回，行为不变。
- 单设备多个 SSE 客户端：各自独立 sessionId 与队列，互不干扰。

## 测试计划

- 直连兼容：POST `/message`（无 sessionId）发 `initialize` 与 `tools/list`，断言 200 且 body 含结果。
- endpoint 格式：GET `/sse` 首个事件是 `endpoint`，data 带 sessionId。
- SSE 回推：GET `/sse` 拿 sessionId，POST `?sessionId` 发 `initialize`，断言 POST 回 202 且 SSE 通道收到 `event: message` 与结果。
- 断连清理：SSE 断开后 hub 中该 session 被移除。
- 全量回归：`npm run test:core`。

## 风险与回滚

- 风险：SSE 线程阻塞占用连接（已 `close_connection = True` 隔离，与媒体流一致）；队列积压（有界加 `put` 超时退回 body）。
- 回滚：改动集中在 server.py 的 `McpSseHub`、`_mcp_sse`、`_mcp_message`，`git` 还原即可，直连兜底不受影响。
