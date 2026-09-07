# Story-0827 macOS 桌面应用 总结

收尾时间：2026-08-28。对应规格 [spec.md](./spec.md)（文末含实施进展与偏差记录）、设计 [technical-design.md](./technical-design.md)。

## 问题描述

LayoutSee V0.1 需要一个可离线运行的 macOS 桌面应用：安全拉起并守护本地 Core，在真实 Android 设备上完成「设备发现 → 画面/操控 → 原子抓取 → 元素定位 → 摘要/诊断 → MCP 接入」，并在服务、设备或媒体链路失败时保留可用内容与恢复路径。起步时四个工程均为待初始化骨架。

## 根因分析（手动测试四轮问题的根因）

1. **Core 启动即 ImportError**：重构把 `main()` 从 `server.py` 移到 `__main__.py`，但 PyInstaller 独立入口 `packaging/entrypoint.py` 未同步——打包产物与源码树入口分离是盲区。
2. **三处死锁**：`threading.Lock` 非重入，`refresh/snapshot`、`resolve_ref`、`settings.update` 在持锁状态下调用本类其他加锁方法；单测全绿掩盖了它（无并发路径覆盖）。
3. **首启动 19.9 秒超时**：双重叠加——PyInstaller onefile 每次启动 7-8 秒自解压（不可接受，切 onedir）；macOS 对新 inode 首次执行的安全评估 8-20 秒（onefile/onedir 都有，与依赖无关，最小 hello-world 包同样中招，ad-hoc 签名/页缓存/换路径均无效）。UIAutoDev「秒开」是因为其后端二进制 inode 数月未变，评估成本只在安装日付过。
4. **「未找到 ADB 工具链」**：Finder 双击启动的 GUI 应用拿不到终端 PATH（仅 `/usr/bin:/bin:/usr/sbin:/sbin`），继承 `process.env` 也无济于事；用户的 adb 在 MacPorts `/opt/local/bin`。

## 方案结论

- 三层架构落地：Electron 壳（进程守护/安全边界）+ 单一 React renderer（由 Core 同源托管）+ Python Core sidecar；READY/info 双重握手 + 每次启动随机 nonce 派生会话令牌（壳/Core 跨语言金样校验）。
- Core 打包用 **PyInstaller onedir**（§23.2 决策门已关闭回写）；壳启动超时 **25 秒 + `CORE_READY_TIMEOUT` 自动重试一次**（§6.2 已回写）；Core 内置 adb 候选路径探测并自动持久化。
- 媒体采用**截图轮询降级模式**先行（UI 明示），scrcpy 实时链路留给后续 Story；写操作统一走每设备串行队列 + 只读门禁 + ActionLog 审计。

## 已完成内容

- M0：四工程、OpenAPI/JSON Schema 契约与生成物漂移检查、假 Core 与场景 DSL。
- M1：壳启动闭环（安全窗口、单实例、启动/错误页、健康检查、重启预算、进程组回收、白名单 IPC、菜单、日志脱敏）。
- M2：Web 路由、主题 Token、错误边界、五 Tab 骨架、双层可访问分隔条。
- M3：真实 Android 主链路（枚举、截图画面与完整交互映射、原子快照、三方联动、XPath、选择器、ref、只读、审计）。
- M4 部分：常用/元素/MCP/布局智能四 Tab 完整，MCP SSE 12 工具；插件仅目录扫描与清单校验（沙箱运行时未实现，UI 已明示）。
- 发行：arm64 未签名本地候选包（DMG），`verify:artifacts` 通过。

## 改动文件（主要）

- `repos/mac/src/main/index.mjs`、`kernel-supervisor.mjs`、`logging.mjs`，壳生命周期/守护/日志
- `repos/mac/src/preload/index.cjs`、`src/shared/handshake.mjs`、`src/bootstrap/index.html`，白名单桥/握手/启动错误页
- `repos/mac/scripts/package.mjs`、`electron-builder.yml`，onedir 打包链
- `repos/core/src/layoutsee_core/`：`server.py`（路由/门禁/SSE/SPA 回退）、`bootstrap.py`（装配工厂）、`adb.py`（含 `find_adb` 探测）、`devices.py`、`snapshots.py`、`xpath.py`、`selectors.py`、`finder.py`、`summary.py`、`diagnostics.py`、`mcp_catalog.py`、`settings.py`、`audit.py`、`errors.py`、`__main__.py`
- `repos/core/packaging/entrypoint.py`、`pyproject.toml`（+elementpath 4.8.0）、`uv.lock`
- `repos/core/tests/`：新增 6 份单测（令牌金样/归一化/XPath/摘要选择器/诊断设置/死锁回归/adb 探测）
- `repos/web/src/`：`main.jsx`、`app/`（AppShell/ShellBridge/theme/错误边界）、`api/client.js`（会话令牌注入）、`components/`（ui/ResizeHandle）、`styles/`（tokens/app）、`features/`（devices、group-preview、workbench 五 Tab、settings）
- `repos/contracts/fixtures/valid/device.json` + 生成物（修复契约漂移）
- `source/{mac,core,web}/`三件套、`docs/story/26-08-28-story-0827-macos-编码与arm64候选包.md`

## 验证结果

- [x] `npm run lint` / `typecheck` / `test:unit` / `build:all` / `verify:artifacts` 全绿（Core 27、壳 8、契约 5 项单测）
- [x] 会话令牌跨语言金样一致（Node 与 Python 各自断言同一 HMAC 值）
- [x] 打包 Core 以 `env -i`（模拟 Finder 无 PATH 环境）启动：枚举出 SM_S9310，adbPath 自动持久化 `/opt/local/bin/adb`
- [x] 打包二进制真机链路：抓取 82 节点、XPath 55 命中 1ms、截图、MCP tools/list 12 工具、摘要 979 tokens、无令牌 `PERMISSION_REQUIRED`、只读 `READ_ONLY_MODE`、SIGTERM 干净退出无端口残留
- [x] 死锁回归测试（线程 join 超时断言）与启动重试路径单测
- [ ] 人工可视化验收：用户进行中，四轮反馈已修复待复测（首次启动仍可能 8-20 秒，启动页有秒数提示，属系统评估成本）
- [ ] Playwright + 假 Core 端到端：未实施（规格要求的主要自动化接缝）
- [ ] scrcpy 实时媒体 / WebCodecs：未实施（当前为截图轮询，暖切换 500ms、15fps 等媒体指标未验收）
- [ ] 插件沙箱 iframe 运行时与 `$u` 桥接：未实施
- [ ] x64、签名、公证、staple、干净机与 10 次启停验证：未实施（M6 门禁，需 Apple Developer 身份与 Intel 机）
- [ ] 性能量化指标（Intel 30 次切换 P95、3000 节点诊断 300ms、连续 dump 内存等）：未实施（M5）
- [ ] 语义摘要「可交互元素无遗漏」：未达标——真机实测 57 个可交互仅纳入 33（保守 Token 估算器在密集页面提前裁剪），需调估算器

## 后续建议

1. 用户复测新包（含超时重试与 adb 探测），确认首次启动提示与设备列表；反馈继续走修复循环。
2. 调优摘要估算器（CJK/ASCII 计权），使典型页面 `omittedInteractive=0`，对照 spec §15 的 1200 token 上限。
3. 建 Playwright + 假 Core 端到端接缝（规格测试决策 §2），把壳生命周期与安全边界测试自动化。
4. 立实时媒体 Story：scrcpy 集成、DedicatedWorker/WebCodecs、背压与截图降级切换。
5. M6 发行前置：申请 Apple Developer 身份（顺带消除首启动评估成本）、准备 Intel 干净机与 x64 构建。
6. 产品补确认 spec 文末六项偏差（超时口径、onedir、截图媒体、插件范围、群控形态、测试接缝现状）后更新规格状态为「已评审」。
