# MCP 未连接时直连本地端点

本兜底仅在确认 MCP 工具通道不可用后使用：UseMcpTool 报 `layoutsee-android-<serial>` 未连接、会话内没有这个 server、或加载后工具列表为空。此时 LayoutSee Core 通常仍在本机运行，直接对它的 HTTP 端点发 JSON-RPC 请求即可，能力与走 MCP 客户端完全一致。优先用 MCP 工具，不要在 MCP 可用时跳过它直接上脚本。

## 为什么会话 MCP 会连不上

历史根因：Core 早期的 SSE 端点是半截实现，`GET .../sse` 只推 endpoint 事件和心跳，响应写在 POST body 不走 SSE。标准 MCP 客户端 POST 后在 SSE 通道等响应，永远等不到，握手挂起，会话内该 server 工具列表为空。直连能用正是因为它直接读 POST body。

修复进展：`server.py` 已加 `McpSseHub` 会话注册，带 `sessionId` 的请求经 SSE 通道回推、POST 回 202，不带 sessionId 仍走 body 同步返回（即下文的直连兜底）。设计见 `specs/mcp-sse-transport/doc.md`。桌面应用的 Core 重启到新代码后会话内 MCP 通道即可正常列出工具；在此之前继续用直连兜底。

## 关键机制：响应在 POST body，不走 SSE

Core 的 SSE 端点是半截的：

- `GET /mcp/android-<serial>/sse` 建立连接后，只回一条 `endpoint` 事件（`data: /mcp/android-<serial>/message`）和每 15 秒一次的心跳，不通过 SSE 推送任何工具结果。
- 真正的调用走 `POST /mcp/android-<serial>/message`，JSON-RPC 响应同步写在这个 POST 的 HTTP response body 里。

所以直连不需要维持 SSE 长连接，也不用读事件流。endpoint 路径可直接推断为 `/mcp/android-<serial>/message`，一个 POST 拿一个结果。

## 三条硬规则

1. 端口：默认 11663，被占用时 Core 落在 11663 到 11672 之间。逐个探测，能对 `tools/list` 正常回 JSON-RPC 的那个就是。
2. device_id：形如 `android-<serial>`。serial 用 `GET /api/v1/devices` 拿（返回 `items[].serial`），或从会话里 `layoutsee-android-<serial>` 的名字截取。
3. 不要带 `Origin` 头。Core 对 `/mcp/**` 校验 Origin：带了就必须同源，不带则放行。curl 默认不带，正好通过；Host 是回环地址，天然合法。

## curl 三步

```bash
BASE=http://127.0.0.1:11663
DEV=android-RFCY41B0EVZ            # 换成实际 serial

# 1. 列设备拿 serial（已知 serial 可跳过）
curl -s "$BASE/api/v1/devices"

# 2. 列工具，确认端口与端点连通
curl -s -X POST "$BASE/mcp/$DEV/message" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# 3. 调工具（先抓快照，再取节点树）
curl -s -X POST "$BASE/mcp/$DEV/message" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"capture_layout","arguments":{}}}'
```

`tools/call` 的返回里，工具真正的结果在 `result.content[0].text`，是一段需要再次解析的 JSON 字符串。

## 封装脚本

`scripts/mcp_call.py` 把端口探测、列设备、JSON-RPC 调用、结果解包都封好，只依赖 Python 标准库：

```bash
python3 scripts/mcp_call.py --list                                  # 列工具
python3 scripts/mcp_call.py capture_layout                          # 抓快照
python3 scripts/mcp_call.py get_layout --args '{"snapshotId":"<id>"}'  # 取指定快照
python3 scripts/mcp_call.py get_current_app --serial RFCY41B0EVZ    # 多设备时指定 serial
```

脚本自动在 11663 到 11672 探测端口，无 `--serial` 时取第一台设备，并把 `result.content[0].text` 解析后打印。

## 失败排查

- 所有端口都拒连或超时：Core 未启动或不在本机。让用户确认 LayoutSee 桌面应用已打开并连上设备。
- `tools/list` 通但 `tools/call` 报 `SNAPSHOT_STALE`：先调 `capture_layout` 再取布局。
- 列设备为空：当前无已连设备，用 `adb devices` 确认。
- 写工具返回 `READ_ONLY_MODE`：设备处于只读模式，属预期保护。
