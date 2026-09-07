# mac 构建与本地候选包

```bash
npm --workspace @layoutsee/mac run build
```

基础构建生成 Electron 主进程（窗口、单实例、导航策略、白名单 IPC、标准 macOS 菜单、主题同步）、sandbox preload、壳内启动/错误页和共享握手模块。

本机候选包使用 Node 24.15.0、Electron 44.0.0、electron-builder 26.15.7、Python 3.12.4 与 PyInstaller 6.22.2（onedir，启动实测见技术设计 §23.2）：

```bash
/Users/jiazihui/.local/node-v24.15.0-darwin-arm64/bin/node repos/mac/scripts/package.mjs
```

打包顺序：构建正式 Web → PyInstaller onedir Core → 暂存 `resources/runtime`（Core 平铺为 `core/layoutsee-core` + `core/_internal`）→ 生成图标与制品清单 → 构建壳制品 → electron-builder 产出 DMG。

Core 启动耗时基线（arm64 实测）：安装后首次启动 8–20 秒（macOS 对 PyInstaller 新 inode 首次执行的安全评估，与依赖无关），其后每次约 0.3 秒。壳启动超时为 25 秒并在 `CORE_READY_TIMEOUT` 时自动重试一次，启动页实时显示已等待秒数；细节见技术设计 §6.2。

输出位置：

- `repos/mac/release/mac-arm64/LayoutSee.app`
- `repos/mac/release/LayoutSee-0.1.0-arm64.dmg`
- `repos/mac/release/LayoutSee-0.1.0-arm64.dmg.blockmap`

制品为未签名、未公证的本地手测包，仅包含 arm64。正式发行仍需 Apple Developer 身份、x64 构建机和发布门禁（签名、公证、staple、Gatekeeper、干净机验证）。

## 壳启动链路

1. 创建窗口并加载壳内启动页（不依赖 Core）。
2. `KernelSupervisor` 以独立进程组拉起 `resources/core/layoutsee-core`，注入 256 位启动随机数。
3. 解析 READY 行（单行 8KiB 上限），请求 `/api/v1/info` 校验 pid、nonce 与三个版本字段。
4. 校验通过后同窗口导航到精确本地 origin；失败进入错误页（重试 / 复制脱敏诊断 / 打开日志目录）。
5. 健康检查每 2 秒一次，连续两次失败进入恢复；重启退避 1/2/4 秒共三次，稳定 60 秒重置预算。
6. 退出时先 `SIGTERM` 进程组，3 秒未退出则 `SIGKILL` 回收全部子孙进程。

日志目录：`~/Library/Application Support/LayoutSee/logs/<day>-{shell,core}.log`，敏感内容自动脱敏。

## 开发调试

```bash
LAYOUTSEE_RESOURCES_DIR=<workspace>/repos/mac/resources/runtime npm --workspace @layoutsee/mac run build
npx electron repos/mac/dist/main/index.mjs
```

`LAYOUTSEE_RESOURCES_DIR` 用于在未打包状态下覆盖 Core 与静态资源位置；生产包不使用开发目录兜底。
