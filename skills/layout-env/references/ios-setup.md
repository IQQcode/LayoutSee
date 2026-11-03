# iOS 环境准备指引

iOS 抓取链路对用户机器**零命令行依赖**（usbmux / 模拟器 loopback 均为系统自带），前置只有三件事：Xcode 体系、被测 App 内嵌 LookinServer、避开单客户端独占。

## 前置清单

| 项 | 检查方式 | 缺口修复 |
| --- | --- | --- |
| Xcode | `xcodebuild -version`（体检 `iosToolchain.xcode`） | App Store 安装 Xcode；仅装 CLT 不够（模拟器截图依赖 Xcode） |
| 模拟器 runtime | `xcrun simctl list runtimes`（体检 `iosToolchain.runtimes`） | Xcode → Settings → Platforms 下载所需 iOS runtime |
| 被测 App 集成 LookinServer | 用 `layout-lookin-server` skill 摸底与集成 | 转 `layout-lookin-server` skill（CocoaPods / SPM / 手动） |
| 官方 Lookin 冲突 | `pgrep -x Lookin`（体检 `lookinConflict`） | 退出官方 Lookin 客户端 |

## 连接链路（端口是硬事实）

| | 真机 | 模拟器 |
| --- | --- | --- |
| 端口 | 47175–47179（USB，经 usbmuxd） | 47164–47169（loopback 直连） |
| 需要数据线 | 是 | 否 |
| 设备列表形态 | `ios-<udid>` | `ios-sim-<port>` |

- LookinServer 版本要求：**协议版本 7**（LookinServer 1.1.8 ~ 1.2.8，当前最新 1.2.8）；不匹配时 Core 报 `LOOKIN_VERSION_MISMATCH`。
- 被测 App 必须 **Debug 构建且前台运行**；切后台监听 socket 会丢，需要 App 冷启动恢复。
- LookinServer **单客户端独占**：官方 Lookin 客户端开着时端口被占，LayoutSee 连不上。
- 真机插上 Mac 系统自动经 usbmuxd 配对，无需额外工具；iOS 日志抓取（`ios-logcat` 插件）要求设备已与 Mac 配对（首连 Finder/Xcode 自动完成；StartService 被拒时用 Xcode/Finder 重新配对）。
- iOS 恒只读：无 tap / 滑动 / 输入注入能力，属产品边界而非环境问题。

## 验收

- `check --json`：`core.devices` 出现 `ios-<udid>`（真机）或 `ios-sim-<port>`（模拟器）。
- 集成完成后若设备不出现，按序排查：App 是否 Debug 构建 → 是否前台运行 → 官方 Lookin 是否已退出（`lookinConflict`）→ 模拟器 App 是否真的在跑（模拟器设备只在「能连上且 app_info 通过」时才枚举）。更多故障形态见 `layout-lookin-server` skill 的 `references/troubleshooting.md`。
