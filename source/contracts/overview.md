# contracts 工程说明

`repos/contracts` 是 Core、Web 与 macOS 壳之间协议的单一事实源。手写源只存在于 `openapi/`、`schemas/`、`compatibility/` 与 `fixtures/`；`generated/` 由命令生成，禁止手改。

当前 M0 覆盖启动握手、统一错误、设备、布局快照、媒体控制、MCP 工具目录、插件清单和假 Core 场景模型。
