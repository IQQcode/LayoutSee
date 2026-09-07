---
title: Story-0827 macOS 应用编码与 arm64 本地候选包
type: story
tags:
  - layoutsee
  - macos
  - electron
  - core
  - web
  - packaging
---

# Story-0827 macOS 应用编码与 arm64 本地候选包

## 本次交付

按 `specs/[Story-0827]-mac-app/spec.md` 落地三层架构的编码，并重新产出 arm64 本地候选包。

### macOS 壳（M1 收尾）

- 重建主进程入口：单实例、标准 macOS 菜单（编辑/视图前进后退/窗口/帮助）、导航策略、权限与下载拒绝。
- 全量白名单 IPC（spec §6.3）：应用信息、Core 会话、重试、脱敏诊断复制、固定日志/插件目录、ADB 路径选择、受信外部帮助、系统主题查询/订阅。
- 会话令牌：由启动 nonce 派生（HMAC-SHA256，"layoutsee-ui-v1"），壳与 Core 共享同一算法并双向金样校验。
- KernelSupervisor：READY 解析、info 二次校验、2 秒健康检查、1/2/4 秒重启退避、稳定 60 秒预算重置、SIGTERM→3 秒→SIGKILL 进程组回收、READY 安全回退探测。
- 日志模块：壳/Core 分文件按天落盘，nonce/凭据/输入自动脱敏；启动页错误态支持复制脱敏诊断。

### Core（M3 主链路）

- 设备注册表（5 秒轮询、增量刷新、离线保留上一轮）、接入诊断、当前应用、应用搜索、每设备串行写队列（5 秒超时 DEVICE_BUSY）。
- 原子快照：冻结写队列 → dump → 截图 → 归一化 → 发布；节点上限 3000、深度 128；幂等键；同步质量 best_effort / context_changed。
- XPath：语法预检（INVALID_XPATH 不发真实请求）、elementpath 引擎、300ms 硬超时、Appium 风格点分标签名改写。
- 稳定选择器生成（真实命中数与稳定标记）、ref 注册表（SNAPSHOT_STALE 与 REF_NOT_FOUND 分离）、确定性语义摘要与六类布局诊断。
- MCP：每设备 SSE 端点（endpoint 事件 + JSON-RPC initialize/tools/list/tools/call/ping），12 工具目录来自运行时。
- 写门禁：会话令牌 + 只读拦截 + ActionLog（requested/result 双记录，文本只记长度与哈希）。
- SPA 回退、严格 CSP、请求体 1MB 上限、设置 0600 原子写入。

### Web（M2 + M3 前端）

- 路由底座（/devices、/group、/devices/:id/workbench/:tab、/settings），刷新恢复与 History 一致。
- 设备页（轮询、复制序列号、诊断弹窗、多选群控、ADB 缺失与三步接入引导）。
- 群控页（多路截图轮询、超阈值降频提示、单格冻结、双击进工作台）。
- 工作台：控制轨（Back/Home/Recents/电源/音量/旋转/抓取/冻结/只读/审查）、设备画面（截图模式标识、tap/swipe/中键 Home/右键 Back/滚轮滑动/键盘输入、悬停坐标、节点高亮叠加层）、双层可访问分隔条（12px/32px/Home/End/双击复位/按设备持久化）。
- 五 Tab：常用（前台应用/启动/停止确认/应用搜索）、插件（清单列表/打开目录）、元素查看（树/属性/画布三方联动、XPath 客户端语法预检、选择器）、MCP（运行时工具目录、.mcp.json/Claude/Cursor/Comate 配置）、布局智能（摘要 + 六类诊断 + 点击定位）。
- 设置（外观/设备与驱动/投屏/安全/关于），主题 token 来自 DESIGN.md，浅色/深色/跟随系统。

### 测试与契约

- Core 单测 21 项、壳 5 项、契约 5 项全部通过；会话令牌跨语言金样一致。
- 修复契约漂移：device fixture 与新 Device schema 对齐后重新生成 TS/Python 模型。
- 新增 elementpath==4.8.0（纯 Python XPath，PyInstaller 友好）并锁定。

## 构建环境

- macOS 26.5.2（arm64）、Node 24.15.0、Python 3.12.4、Electron 44.0.0、electron-builder 26.15.7、PyInstaller 6.22.2。
- 制品：`repos/mac/release/LayoutSee-0.1.0-arm64.dmg`（约 144MB，未签名未公证）、`release/mac-arm64/LayoutSee.app`。
- `verify:artifacts` 通过；`npm run lint / typecheck / test:unit / build:all` 全部通过。

## 已知边界（本 Story 未实现，后续 Story 承接）

- scrcpy 实时媒体链路与 WebCodecs 解码：当前为截图轮询模式，UI 有明确"截图模式"标识。
- 插件沙箱 iframe 与 `$u` 能力桥接：已完成目录扫描与清单校验，运行时未开放（UI 有明示）。
- MCP 已提供 SSE + JSON-RPC 12 工具；性能基准、真机矩阵、签名公证、x64 与干净机验证仍属发布门禁。
- Playwright + 假 Core 端到端测试基建未进入本 Story。

## 下一步

用户手动功能测试（启动、设备发现、投屏截图模式、抓取、元素定位、XPath、摘要诊断、MCP、只读）；测试反馈修复后再推进 M5 动效、M6 双架构发行。

## 手动测试反馈修复（第二轮：启动超时）

用户实测新包仍超时（CORE_READY_TIMEOUT，15 秒未就绪）。排查结论：

1. 修复后的 Core 二进制本身启动过慢：PyInstaller onefile 在本机**每次启动需 7-8 秒自解压**，首启动实测 19.9 秒，超过 15 秒硬超时；onedir 首启动 8.1 秒（新 inode 一次性系统评估，ad-hoc 签名无效）、热启动 0.27 秒。
2. 按 spec §23.2 决策门切换为 **PyInstaller onedir**（技术设计文档已回写）：制品布局改为 `Resources/core/layoutsee-core` + `Resources/core/_internal/`，壳 spawn 路径不变；`package.mjs` 与 `electron-builder.yml`（core 资源全量拷贝）同步更新。
3. 清理了旧版应用残留 Core 进程（14:03 与旧会话假 Core），释放 33299 端口。

打包二进制验证：首次启动 8.1 秒内输出 READY、真机枚举/抓取/XPath/MCP/门禁/退出全部通过；二次启动 0.27 秒。

## 手动测试反馈修复（第三轮：首启动耗时与 UIAutoDev 对比）

用户反馈新 inode 首次执行实测 19.9s，而 UIAutoDev Desktop 秒开。对照实验结论：

- 慢的不是我们的代码或依赖：最小 hello-world PyInstaller 包新副本首执行同样要 2.7–6.5s；系统签名二进制（/bin/echo、python3.12）与 UIAutoDev 的单文件 Go 后端（1.87s）不受影响。这是 macOS 对 PyInstaller 结构（多文件、ad-hoc 签名）按新 inode 首次执行的安全评估，页缓存、路径、ad-hoc 签名均无法绕过。
- UIAutoDev 秒开是因为其后端二进制 7 月 31 日安装后 inode 从未变化，评估成本只在首次安装时付过一次；LayoutSee 反复出新包导致每次都重新付费。
- 应对（已实现并验证）：壳启动超时 15s→**25s** + `CORE_READY_TIMEOUT` **自动重试一次**（评估完成后第二次执行即 0.3s）+ 启动页实时显示已等待秒数；新增 `tests/kernel-supervisor.test.mjs` 验证自动重试路径（mac 测试 5→8 项全过）。
- 预期体验：安装后**首次启动约 8–20 秒**（启动页有进度与秒数，非卡死），**之后每次 0.3 秒秒开**，与 UIAutoDev 同模式。技术设计 §6.2 与 §23.2 已回写；彻底消除一次性成本需 Developer ID 签名或换 Nuitka，属 M6 发行门禁。

## 手动测试反馈修复（第四轮：Finder 启动找不到 ADB）

用户终端/Android Studio 里 adb 可用（MacPorts `/opt/local/bin/adb`），但应用显示「未找到 ADB 工具链」。根因：Finder 双击启动的 GUI 应用拿不到终端 PATH（只有 `/usr/bin:/bin:/usr/sbin:/sbin`），继承 process.env 也没用。修复：

1. Core 增加 `find_adb()` 候选路径探测（MacPorts/Homebrew/Android SDK platform-tools），未显式配置时按序兜底；探测命中后自动持久化到 `settings.json` 的 `adbPath`（诊断与后续启动稳定）。
2. 壳 spawn Core 时把 `/opt/local/bin`、`/opt/homebrew/bin`、`/usr/local/bin` 补进子进程 PATH（为后续 scrcpy 等工具同样受益）。
3. 新增 `test_adb_discovery.py`（3 项，Core 27 项全过）。

验证：打包 Core 用 `env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin` 模拟 GUI 环境启动，设备页正常枚举 SM_S9310，设置中 adbPath 自动记录为 `/opt/local/bin/adb`。

## 手动测试反馈修复（第一轮）

1. **Core 启动即崩溃（CORE_EXITED_1）**：打包入口 `packaging/entrypoint.py` 仍调用已迁走的 `server.main()`。已改为 `layoutsee_core.__main__.main`，并用打包二进制验证 READY 输出。
2. **非重入锁嵌套死锁**（设备页/设置/ref 解析会挂死）：`DeviceRegistry.refresh/snapshot` 在锁内调用 `list_devices()`、`SnapshotStore.resolve_ref` 在锁内查 token、`SettingsStore.update` 在锁内调 `get()`。三处已重构为单次加锁；新增 `test_locking_regression.py`（线程 join 超时断言，Core 24 项全过）。
3. **子进程环境整体替换**：壳 spawn Core 时改为继承 `process.env` 再覆盖，避免打包后从 Finder 启动丢失 PATH/HOME。
4. **错误页文案**：`CORE_EXITED_*` 退出码映射为友好说明（含退出码），便于用户自行排查。
5. **ref 解析修正**：refs 为 nodeKey→ref 映射，resolve_ref 改为按值反查；补正回归测试数据。

重新打包产物为 `repos/mac/release/LayoutSee-0.1.0-arm64.dmg`；打包二进制已通过 info/devices/SPA 回退接口验证。注意：本机旧版应用残留进程仍占用 33299 端口，新包会按设计自动递增端口，测试前建议退出旧版应用并确认 `pgrep -f layoutsee-core` 无残留。
