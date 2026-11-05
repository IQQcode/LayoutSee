# LayoutSee 环境体检 Skill（layout-env）

装好 LayoutSee 之后的一键环境配置：一条命令体检 Android / iOS 两端缺口，按缺口修复，直到设备列表可用。

## 概览

- **体检项**：LayoutSee.app 安装、Core 服务与在线设备、ADB（探测 + 版本 + 设备）、settings.json 的 `adbPath`、Xcode 与模拟器 runtime、booted 模拟器、CocoaPods、官方 Lookin 客户端冲突
- **配置项**：把 adb 路径写入 `~/Library/Application Support/LayoutSee/settings.json`（仅在 LayoutSee 未运行时）
- **修复指引**：Android（安装 ADB、USB 调试授权）与 iOS（Xcode、模拟器 runtime、LookinServer 前置）分文档展开

## 快速上手

```bash
python3 -I scripts/env_check.py check          # 人读报告
python3 -I scripts/env_check.py check --json   # AI / 脚本消费，exit 0 全绿 / 1 有缺口
python3 -I scripts/env_check.py set-adb /opt/homebrew/bin/adb
```

## 环境依赖

- macOS；脚本仅依赖 Python 3 标准库。
- 完整能力需要 LayoutSee 桌面应用（[官网下载](https://layoutsee-site.vercel.app/download.html)）。
- iOS 被测 App 集成 LookinServer 属于工程改动，见 `layout-lookin-server` skill。

## 文档

- 工作流程与决策顺序：`SKILL.md`
- Android 环境修复：`references/android-setup.md`
- iOS 环境准备：`references/ios-setup.md`
- 集成 LookinServer：`layout-lookin-server` skill
- 读取与分析视图树：`layout-see` skill
