# 连接类故障排查

集成完成但 LayoutSee 侧异常时按此排查。环境类（Xcode / 模拟器 runtime / ADB）见 `layout-env` skill。

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| Core 报 `LOOKIN_VERSION_MISMATCH` | App 内 LookinServer 协议版本 ≠ 7 | 摸底看已集成版本；统一到 `1.2.8`（协议 7 覆盖 1.1.8~1.2.8），重新构建运行 |
| 设备列表不出现 iOS 设备 | 未集成 / 非 Debug 构建 / App 未前台 | 依次确认：摸底 verdict → 构建配置是 Debug → App 前台运行；模拟器设备只在「连得上且 app_info 通过」时枚举 |
| 设备列表不出现，`lookinConflict=conflict` | 官方 Lookin 客户端占用端口 | LookinServer 单客户端独占，退出官方 Lookin |
| 连接超时（-404）/ `PingFailForBackgroundState`（-407） | App 切后台或被 Xcode 断点暂停 | App 调回前台；被暂停则恢复运行；监听 socket 已丢时**冷启动 App** |
| 属性面板看不到 Swift 属性名 | CocoaPods 集成未加 `:subspecs => ['Swift']` | 按 cocoapods.md 补 Swift subspec（SPM 集成无此问题） |
| 编译报 duplicate symbols | 老版本 LookinServer（< 1.0.5） | 升到 1.2.8 |
| iOS 高系统版本启动崩溃（UIGraphicsBeginImageContext 零尺寸） | ≤ 1.2.1 的已知崩溃 | 升到 1.2.8 |
| 真机日志（ios-logcat 插件）没有历史记录 | syslog_relay 只有实时流 | 属已知限制；StartService 被拒时用 Xcode/Finder 重新配对 |
| 日志大量 `<private>` | os_log 系统级脱敏 | 属已知限制，非集成问题 |

## 端口速查（排查防火墙/占用用）

| 链路 | 端口 |
| --- | --- |
| 真机（USB，经 usbmuxd） | 47175–47179 |
| 模拟器（loopback 直连） | 47164–47169 |

## 验收口径

App 以 Debug 配置运行且前台时，`layout-env` skill 的 `env_check.py check --json` 里 `core.devices` 应出现 `ios-<udid>`（真机）或 `ios-sim-<port>`（模拟器）；随后用 `layout-see` skill `capture_layout` 拿到快照即为全链路通过。
