# MCP SSE Transport 改造实施总结

## 变更

- `repos/core/src/layoutsee_core/server.py`：
  - 新增 `import threading`、`_McpSession` 与 `McpSseHub`（线程安全的 sessionId 到发送队列注册表）。
  - `LoopbackServer` 持有 `mcp_hub`，所有 handler 线程共享。
  - `_mcp_sse`：注册 session，`endpoint` 事件带 `sessionId`，循环从 outbox 取消息以 `event: message` 推回，心跳降级为队列 15 秒超时，断连在 `finally` 清理。
  - `_mcp_message`：抽出 `_deliver_mcp_response`，带 sessionId 走 SSE 回推并回 202，无 sessionId 退回 body 同步返回。
- `repos/core/tests/test_mcp_sse.py`：新增 5 个测试（注册表增删查、直连 initialize、直连 tools/list、未命中 session 兜底 body、命中 session 投递 202 到 outbox）。

## 验证

- `npm run test:core`：104 项全通过，无回归。
- 单跑 `test_mcp_sse`：5 项通过。
- 端到端（真机 `android-RFCY41B0EVZ`）：模拟标准 MCP SSE 客户端，`GET /sse` 拿 sessionId，`POST ?sessionId` 发 initialize 与 tools/list 均回 202，SSE 通道收到对应响应，tools/list 返回 13 个工具。
- 直连兜底（`skills/layout-see/scripts/mcp_call.py`，不带 sessionId）行为不变。

## 兼容性与部署

- 带 sessionId 走 SSE 回推（标准客户端），不带 sessionId 走 POST body（脚本直连），二者共存。
- 会话内 MCP 通道要待 LayoutSee 桌面应用的 Core 重启到新代码后才生效；此前继续用直连兜底。

## 未决

- 未引入 2025 版 streamable-http，如后续客户端需要再评估。
