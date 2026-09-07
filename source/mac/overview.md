# mac 工程说明

`repos/mac` 是 macOS 桌面壳工程。主进程只负责窗口、生命周期与系统能力白名单，不承载设备业务逻辑；正式 Web 构建产物由 Core 同源托管，壳在握手通过后导航到精确本地 origin。

已落地能力：

- Electron 安全窗口：1440×900 默认、1280×800 最小、`hiddenInset` 标题栏、sandbox preload（上下文隔离、关闭 Node 集成与 webviewTag）。
- 单实例锁、壳内启动/错误页（重试、复制脱敏诊断、打开日志目录）。
- `KernelSupervisor`：READY 解析、`/api/v1/info` 身份与版本二次校验、2 秒健康检查、1/2/4 秒重启退避、稳定 60 秒预算重置、SIGTERM → 3 秒 → SIGKILL 进程组回收。
- 白名单 IPC：应用信息、Core 会话（含会话令牌）、重试、脱敏诊断、固定日志/插件目录、ADB 路径选择、受信外部帮助入口、系统主题查询与订阅。
- 导航策略：只允许启动页与本次握手 origin；拒绝弹窗、权限请求、下载、附加 webview。
- 标准 macOS 菜单（编辑、视图前进后退与刷新、窗口、帮助），`Cmd+[` / `Cmd+]` 与浏览器 History 一致。
- 会话令牌：由启动 nonce 派生（HMAC-SHA256），经 preload 注入正式 UI，Core 侧恒定时间比较；普通本地网页无法获得写权限。
- 日志：壳与 Core 分文件按天落盘，nonce 与凭据自动脱敏。

模块：`src/main/index.mjs`（生命周期与 IPC）、`src/main/kernel-supervisor.mjs`（Core 守护）、`src/main/logging.mjs`（脱敏日志）、`src/preload/index.cjs`（白名单桥）、`src/shared/handshake.mjs`（READY/info/令牌派生，与 Core 共用算法）、`src/bootstrap/index.html`（启动/错误页）。

Electron 44.0.0、electron-builder 26.15.7 与 PyInstaller 6.22.2 是已成功构建的本地候选版本；在人工功能测试、签名、公证和双架构门禁完成前，不视为正式发布结论。
