# Android 环境修复指引

Android 端只有一个硬性外部依赖：`adb`。其余全是手机侧操作。

## 1. ADB 的来源与 LayoutSee 的探测规则

LayoutSee Core 探测顺序（与 `repos/core/src/layoutsee_core/adb.py` 的 `find_adb` 一致）：

1. 设置里配置的 `adbPath`（`~/Library/Application Support/LayoutSee/settings.json`）
2. `PATH` 里的 `adb`（`shutil.which`）
3. 候选路径，按序：
   - `/opt/local/bin/adb`（MacPorts）
   - `/opt/homebrew/bin/adb`（Homebrew，Apple Silicon）
   - `/usr/local/bin/adb`（Homebrew，Intel）
   - `~/Library/Android/sdk/platform-tools/adb`（Android Studio SDK）
   - `~/Android/Sdk/platform-tools/adb`

Core 启动时若未配置 `adbPath` 且候选探测命中，会**自动回填** settings——标准位置安装的 adb 通常无需任何配置。`env_check.py check` 的 `adb.source` 字段会标注命中来源（`settings` / `PATH` / `candidate`）。

## 2. 安装 ADB

- **Homebrew（推荐）**：`brew install android-platform-tools`。执行前征得用户同意。
- **无 Homebrew / 手动**：从官方 [platform-tools 发布页](https://developer.android.com/tools/releases/platform-tools) 下载 macOS 版 zip，解压出 `adb` 后用 `set-adb` 指路径：

  ```bash
  python3 -I scripts/env_check.py set-adb /path/to/platform-tools/adb
  ```

- Android Studio 用户：SDK 默认在 `~/Library/Android/sdk/platform-tools/adb`，已在候选路径内，装好即可。

`set-adb` 只在 LayoutSee **未运行**时接受写入（运行中拒写 exit 2，防止运行中的 Core 用内存态覆盖）；运行中想改路径，请在应用设置页选择。

## 3. 手机侧三步

1. 开启开发者选项与 USB 调试（设置 → 关于手机 → 连点版本号 7 次 → 开发者选项 → USB 调试）。
2. 用支持**数据传输**的线连接 Mac（仅充电线枚举不到设备）。
3. 手机弹出「允许 USB 调试」时确认授权；未确认则 `adb devices` 显示 `unauthorized`。

## 4. 验收

- `check --json`：`adb.devices` 非空且 `state=device`；`core.devices` 出现 `android-<serial>`。
- 仍看不到设备时按 `adb.devices[].state` 排查：`unauthorized` → 手机确认授权；`offline` → 重插数据线；`device` 但 Core 列表没有 → 确认 Core 在跑（`check.core.status`），必要时重启应用。
