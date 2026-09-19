# repos/mac  mac 桌面壳工程

LayoutSee macOS 桌面壳（Shell）目标工程，采用 Electron 技术栈。

## 定位

壳负责桌面应用的窗口、进程守护、发行与系统集成，业务 UI 由 `repos/web` 的构建产物承载（WebView 渲染）。

- 内核（Core）守护：拉起 / 守护 Python 内核服务（复用 uiautodev 设备接入层二开，默认 127.0.0.1:11663）。
- 窗口管理：主窗口加载 `repos/web` 构建产物，支持多设备群控窗口。
- 发行集成：打包（dmg）、自动更新、菜单栏、系统集成（遵循 DESIGN.md 的 Apple 品质感要求）。

## 技术栈规划

- Electron（主进程 + preload + renderer）。
- 主进程负责内核拉起与 IPC 桥，renderer 加载 web 端构建产物。

## 目录结构（骨架）

```text
repos/mac/
├── README.md          ← 本文件
├── src/
│   ├── main/          ← Electron 主进程（窗口、内核守护、IPC、进程生命周期）
│   ├── preload/       ← 预加载脚本（contextBridge 暴露安全 API）
│   └── renderer/      ← 渲染进程入口（加载 web 构建产物，规划中）
├── build/             ← 打包资源（应用图标、dmg 背景等）
└── scripts/           ← 构建 / 打包 / 签名脚本
```

## 当前实现状态

- [x] 初始化根 workspace 与 `package.json`。
- [x] 实现严格 READY 解析、版本检查和 `/api/v1/info` 身份一致性校验。
- [x] 提供壳层启动占位页与基础制品构建。
- [x] 锁定本地候选版本：Electron 44.0.0、electron-builder 26.15.7、PyInstaller 6.22.2。
- [x] 实现主进程骨架：单实例、安全窗口、启动页、Core 拉起、READY/info 校验和进程组回收。
- [x] 实现 sandbox preload 白名单桥与精确 origin 导航限制。
- [x] 生成 arm64 `.app` 与未签名 DMG，供本机手动测试。
- [x] x64 / arm64 双架构打包链（`npm run package:mac:all`；x64 在 arm64 构建机经 Rosetta + python-build-standalone x86_64 解释器产出）。
- [ ] Apple 签名、公证、staple 与干净机门禁。

## 打包架构

- 应用整体要求 macOS ≥ 13.0（Ventura，Electron 44 框架硬下限，见 `electron-builder.yml` 的 `minimumSystemVersion`）。
- 双架构各自独立 DMG，归档在 `release/mac-arm64/` 与 `release/mac-x64/`：Apple Silicon 装 `mac-arm64/` 下的包，Intel 装 `mac-x64/` 下的包（目录内同时有解包 .app 便于直接调试）。
- Core（PyInstaller onedir）与 Electron 架构必须一致：`scripts/package.mjs` 按 `--arch` 分别构建再打包，x64 解释器来自 python-build-standalone（缓存 `build/python-x64/`，首次自动下载，`PBS_MIRROR` 可换源）。

## 路由

- Web 端工程：`../web`
- 内核说明：`../../source/uiautodev/overview.md`
- 视觉规范：`../../docs/designs/DESIGN.md`
