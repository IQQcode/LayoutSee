# core 工程说明

`repos/core` 是第一方本地 Core：在 `127.0.0.1` 原子绑定端口（33299 起最多尝试 10 个）、输出严格 READY 行，并通过本次启动的 256 位随机数完成身份握手。业务上覆盖 Android 真实设备主链路：

- **设备**：后台 5 秒增量枚举、手动刷新、接入诊断、当前应用、已安装应用、离线保留上一轮结果。
- **快照**：原子抓取（冻结写队列 → dump → 截图 → 归一化 → 建索引），节点上限 3000、深度 128，`LayoutSnapshot` 是 UI 与 Agent 的唯一布局事实源。
- **查询**：XPath（语法预检、隔离线程 300ms 硬超时、点分标签名改写）、稳定选择器生成、`ref` 注册表（旧快照 `SNAPSHOT_STALE`，非法 `REF_NOT_FOUND`）。
- **智能**：确定性语义摘要（短 `ref`、保守 Token 估算、partial 语义）与六类布局诊断（重叠、遮挡、越界、触控热区、文本截断、隐形可交互），全部离线可复现。
- **写操作**：UI、MCP、插件共用每设备串行队列、只读门禁与 ActionLog（JSONL + fsync，文本只记长度与哈希）。
- **MCP**：每设备 `/mcp/{deviceId}/sse` 端点（SSE + JSON-RPC），12 工具目录来自运行时 `tools/list`。
- **媒体**：当前为截图轮询模式（`/api/v1/devices/{id}/screenshot`）；scrcpy 实时链路属后续 Story。

安全基线：生产只监听 IPv4 回环；UI 写请求必须携带由 nonce 派生的会话令牌（HMAC-SHA256，恒定时间比较）；静态资源带严格 CSP；请求体与表达式均有尺寸上限。设置与审计文件 0600 原子写入，数据目录固定为 `~/Library/Application Support/LayoutSee`（可用 `LAYOUTSEE_DATA_DIR` 覆盖）。

## 模块

| 模块 | 职责 |
|---|---|
| `bootstrap.py` | 服务装配工厂，真实 Core 与假 Core 共用 |
| `server.py` | 路由、envelope、会话校验、SPA 回退、SSE |
| `adb.py` | subprocess 版 ADB 适配器（枚举、dump、截图、动作） |
| `devices.py` | 设备注册表 + 每设备写队列（DeviceGate） |
| `snapshots.py` | 抓取协调、节点归一化、快照缓存与 ref 注册表 |
| `xpath.py` | XPath 校验、改写与查询 |
| `selectors.py` / `finder.py` | 选择器候选与元素查找 |
| `summary.py` / `diagnostics.py` | 语义摘要与六类诊断 |
| `mcp_catalog.py` | 12 工具目录与调度（读写门禁统一入口） |
| `settings.py` / `audit.py` | 原子设置存储与审计日志 |
