---
name: layout-env
description: >
  LayoutSee 环境一键体检与配置：检测 LayoutSee 桌面应用与 Core 服务、探测 ADB 并把 adb 路径写入
  LayoutSee 设置（settings.json 的 adbPath）、检查 iOS 工具链（Xcode、模拟器 runtime、CocoaPods）、
  提醒官方 Lookin 客户端冲突，最后复检设备列表确认可用。用户提到环境配置、一键配置、装环境、
  初始化环境、adb 未找到、ADB_NOT_FOUND、adb 路径映射、设备列表为空、连不上设备、装好 LayoutSee
  之后、检查环境/环境检查、iOS 环境准备时使用。把 LookinServer 集成进 iOS 工程走
  layout-lookin-server skill；读取与分析视图树走 layout-see skill；本 skill 不做布局分析、
  不改用户工程代码、不动 LayoutSee 产品代码。
---

# LayoutSee 环境体检与一键配置

为「装好 LayoutSee 之后能跑起来」负责：一次体检给出 Android / iOS 两端缺口，按缺口修复，再复检收口。核心原则：**先体检再动手；写配置前确认 LayoutSee 未运行；每步修复后复检。**

## 触发条件

| 场景 | 行为 |
| --- | --- |
| 装好 LayoutSee 想开始用 / 要求一键配置环境 | 体检 → 按缺口修复 → 复检 → 汇报 |
| 报 ADB_NOT_FOUND / adb 未找到 / 设备列表为空 | 先体检确认缺口，再按 Android 修复走 |
| 要求配置 adb 路径 / 路径映射 | 用 `set-adb` 写入（LayoutSee 必须未运行） |
| iOS 设备不出现 / 准备 iOS 环境 | 按 iOS 修复走；涉及集成 LookinServer 时转 `layout-lookin-server` skill |
| 要读视图树、分析布局、操作设备 | 不触发本 skill，转 `layout-see` |

## 标准操作顺序

1. **体检**：`python3 -I scripts/env_check.py check --json`（JSON 供分析；给人看可省略 `--json`）。exit code：0 全绿；1 有缺口。
2. **按缺口修复**（见下节）。动用户机器前先说明要做什么；安装类命令（`brew install` 等）先征得同意再执行。
3. **复检**：再跑一次 `check --json`，确认缺口收敛。
4. **汇报**：结论 + 剩余必须由人完成的动作（手机上点授权弹窗、在 Xcode 里下载模拟器 runtime、退出官方 Lookin 等）。

## 脚本能力（scripts/env_check.py，仅标准库）

```bash
python3 -I scripts/env_check.py check [--json] [--port N]   # 体检，exit 0 全绿 / 1 有缺口
python3 -I scripts/env_check.py set-adb <adb 路径>          # 写入 settings.json 的 adbPath
```

`check` 输出的 `checks` 节：

| 键 | 内容 | 缺口判断 |
| --- | --- | --- |
| `layoutseeApp` | /Applications 与 ~/Applications 是否有 LayoutSee.app | `status=missing` → 提示官网下载 |
| `core` | 端口 11663–11672 探测 Core（`/api/v1/devices`），回传在线设备 `deviceId/serial/platform` | `status=stopped` → 请打开桌面应用 |
| `settings` | `~/Library/Application Support/LayoutSee/settings.json` 是否存在及 `adbPath` 现值 | 仅信息，不算缺口 |
| `adb` | which + 候选路径探测（与 Core `adb.py` 同一清单）、version、`devices -l` 解析 | `status=missing` → 装 ADB；`devices` 空 → 连手机 |
| `iosToolchain` | `xcodebuild -version`、`xcrun simctl` 可用性、已装 runtime、booted 模拟器 | 缺 Xcode / runtime 时在 `hints` 给指引 |
| `cocoapods` | `pod --version` | `status=missing` → 仅 iOS CocoaPods 集成时需要 |
| `lookinConflict` | `pgrep -x Lookin` 官方客户端是否在跑 | `status=conflict` → 请退出 Lookin |

`summary` 节给出 `androidReady` / `iosReady` 与按优先级排序的 `actions` 建议；修复动作以它为清单，不要凭空发挥。

`set-adb` 行为：校验路径是可执行文件 → 检查 LayoutSee 是否在运行（在跑则拒写，exit 2；提示改用应用内设置页）→ 读 `settings.json` 合并写入 `{"adbPath": ...}`（保留其余键，原子写，0600，exit 0）；路径非法 exit 3。`LAYOUTSEE_DATA_DIR` 环境变量可重定向数据目录（与 Core 同约定，用于演练）。

## 修复动作

- **Android**（ADB 安装、手机侧授权、adbPath 语义）：见 [android-setup.md](references/android-setup.md)。
- **iOS**（Xcode / 模拟器 runtime / LookinServer 前置 / 官方 Lookin 冲突 / 端口）：见 [ios-setup.md](references/ios-setup.md)。其中「被测 App 集成 LookinServer」是独立工程改动，转 `layout-lookin-server` skill 完成。
- **安装 ADB**：`brew install android-platform-tools`（Homebrew 缺失或用户偏好手动时，按 android-setup.md 的官方 platform-tools 方式 + `set-adb` 指路径）。

## 输出要求

- 最终汇报包含：各端就绪状态、本次做了什么（含用户已同意的安装类命令）、剩余人工步骤。
- 引用体检事实（如 `adb devices` 的 serial 与 state），不要凭空断言设备状态。

## 安全边界

- 写文件只允许 `settings.json` 的 `adbPath` 一个键（保留其余内容）；不碰用户工程代码、不碰产品代码。
- 网络只访问回环地址的本地 Core；不向任何远端发送数据。
- 子进程只用 argv 列表调用（脚本内已封装）；安装类命令执行前必须征得用户同意。
