---
name: layout-lookin-server
description: >
  把 LookinServer 自动集成进用户自己的 iOS 工程，让 LayoutSee 能抓取该 App 的运行时视图树：
  摸底工程（CocoaPods / SPM、Swift / OC、build configuration 名），按路径改 Podfile 或
  project.pbxproj，跑 pod install / 依赖解析验证，指导构建 Debug 版并验收。用户提到
  LookinServer、集成 Lookin、接入 Lookin、内嵌 LookinServer、iOS 布局抓取准备、iOS 设备
  抓不到、给 App 加调试框架、pod 'LookinServer'、SPM 集成 LookinServer 时使用；也覆盖集成
  后的连接类故障排查（LOOKIN_VERSION_MISMATCH、后台丢监听、单客户端独占）。只做集成与验收：
  读视图树走 layout-see skill；环境体检（Xcode / 模拟器 runtime / ADB / adbPath）走
  layout-env skill；本 skill 不分析布局、不改业务代码、不碰 Android。
---

# LookinServer 自动集成

把 LookinServer 以 Debug 配置集成进用户的 iOS App 工程，使其能被 LayoutSee 枚举与抓取。核心原则：**只动集成文件（Podfile / project.pbxproj），版本与写法按事实源，改前可回滚，改后必须构建验证。**

## 触发条件

| 场景 | 行为 |
| --- | --- |
| 要求把 LookinServer 集成进 iOS 工程 / 让 LayoutSee 能抓 iOS App | 走标准流程 |
| iOS 设备抓不到、LayoutSee 里不出现 iOS 设备 | 先判断是否未集成：跑摸底脚本，未集成则集成，已集成转 troubleshooting |
| 集成后连不上、版本不匹配、后台丢监听 | 按 troubleshooting 处理 |
| 读视图树、分析布局 | 转 `layout-see`；环境体检转 `layout-env` |

## 版本与配置事实（不要凭记忆改）

- **集成版本 `1.2.8`**（LookinServer 当前最新，2024-04-06 后无新版）。LayoutSee Core pin 协议版本 7，对应 LookinServer 1.1.8 ~ 1.2.8；锁定 `1.2.8` 避免未来协议漂移。
- **仅 Debug**：CocoaPods 靠 `:configurations => ['Debug']`（pod 内宏是无条件定义的，漏了它 Release 会真编译进去）；SPM 的 Release 裁剪由包内宏完成，全配置引入即可。
- **无需任何 Info.plist key、无需写集成代码**（hook 机制自启动）；deployment target ≥ iOS 9.0。
- **禁止 1.0.6 以下版本**（官方红字警告的线上事故）；静态库集成（不开 `use_frameworks!`）需 ≥ 1.1.0。
- 端口（排查用）：真机 47175–47179（usbmux），模拟器 47164–47169（loopback）。

## 标准流程

1. **摸底**：`python3 -I scripts/inspect_ios_project.py <工程目录>`，输出 JSON（Podfile / .xcodeproj / Package.swift、各工程 build configuration 名、Swift/OC 占比、是否已集成、verdict）。拿 `verdict` 与 `configurations` 再动手。
2. **选路径**：
   - `verdict = cocoapods-integrated` / `spm-integrated`：已集成，核对版本是否 1.2.8，不匹配则升级，然后直接进验收。
   - `recommend-cocoapods`（有 Podfile）：按 [cocoapods.md](references/cocoapods.md) 改 Podfile → `pod install`。
   - `recommend-spm`（有 .xcodeproj 无 Podfile）：按 [spm.md](references/spm.md) 加 SPM 依赖（Xcode UI 或直改 pbxproj）。
   - 无 CocoaPods 且工程也未用 SPM 时，先问用户偏好（装 CocoaPods 走 CocoaPods 路径，或直接 SPM），不要替用户装包管理器。
3. **验证**：CocoaPods 看 `Podfile.lock` 出现 `LookinServer (1.2.8)`；SPM 跑 `xcodebuild -resolvePackageDependencies` 成功。改动涉及 `project.pbxproj` 时，先建议用户提交或备份，改完展示 diff。
4. **运行验收**：指导用户构建 **Debug** 配置并运行 App，保持前台；iOS 侧退出官方 Lookin 客户端。用 `layout-env` skill 的 `env_check.py check` 看 `core.devices` 是否出现 `ios-<udid>`（真机）或 `ios-sim-<port>`（模拟器）；出现即集成成功，可用 `layout-see` skill 抓取验证。
5. **故障**：连不上或行为异常按 [troubleshooting.md](references/troubleshooting.md) 处理。

## 输出要求

- 汇报集成方式（CocoaPods / SPM）、版本、改动的文件与内容、构建验证结果、验收步骤与结果。
- 涉及 `:configurations` 时给出所选 configuration 名与来源（工程实际配置名列表），说明为什么不是默认的 `['Debug']`。

## 安全边界

- 只改 `Podfile` 与 `project.pbxproj`（以及运行 `pod install` / `xcodebuild` 验证命令）；不碰业务代码、不碰 Release 配置。
- 直改 pbxproj 前确认工程已有版本管理或先做副本；改完展示 diff。
- 安装 CocoaPods / 修改依赖属用户工程变更，先征得同意。
- 不向远端发送任何数据；脚本只读本地工程。
