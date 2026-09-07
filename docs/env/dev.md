# dev.md 本地开发环境

LayoutSee 本地开发环境说明。覆盖工具链、设备链路与常见坑位。

## 工具链

| 组件 | 版本要求 | 用途 |
|------|---------|------|
| Node.js | 18+ | layoutsee-prototype 前端原型（Vite 6 + React 19） |
| Python | 3.8+ | uiautodev 内核（布局抓取与 API 服务） |
| ADB | 随 Android SDK | Android 抓取链路（uiautomator dump） |
| uiautomator2 | pip 安装 | Android UI 自动化服务 |
| WDA | 设备侧 | iOS 视图抓取与操控（按需） |
| HDC | 随 HarmonyOS SDK | 鸿蒙抓取链路（按需） |

## 快速启动

```bash
# 前端原型
cd source/layoutsee-prototype
npm install
npm run dev          # Vite dev server

# 内核服务（uiautodev）
pip install uiautodev
python3 -m uiautodev  # 默认 HTTP 端口 20242
```

## 设备接入

- Android：`adb devices` 确认设备在线，uiautodev 默认走 uiautomator2 driver（`UIAUTODEV_USE_ADB_DRIVER=1` 可切换 adb driver）。
- iOS：需设备侧安装 WDA。
- 鸿蒙：需 HDC 连接（后续版本支持）。

## 已知坑位（Agent 容易犯的错）

- **不要**尝试在本地完整启动 MySQL / Redis 做端到端测试，本产品无服务端依赖。
- 多模块本地 Debug 时注意端口冲突：uiautodev 默认 20242，前端 Vite 默认 5173，内核 Core 规划默认 127.0.0.1:33299。
- uiautodev 为第三方开源内核，禁止直接在其仓库内改动代码，二开产物应落在 layoutsee-prototype 或独立二开目录。

## 路由

- 各仓库详细构建与调试：`../../source/layoutsee-prototype/setup.md`、`../../source/uiautodev/setup.md`
