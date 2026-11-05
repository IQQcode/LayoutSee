# 22.8 一键环境配置：layout-env 与 layout-lookin-server Skill 设计

状态：实施完成（summary 见同目录 `summary.md`）。

## 背景与目标

新用户装完 LayoutSee 后仍需手动处理两类环境：

1. **Android**：安装 ADB；非标准安装位置时还要在设置里指定路径。
2. **iOS**：在自己的被测 App 内以 Debug 配置集成 LookinServer，这是纯工程改动，用户要自己查文档。

目标：把两条配置链路收敛为「AI 会话一键完成」，交付两个 workspace skill（决策：**只做 skill，不做 npm 包**，不动产品代码）。

- `skills/layout-env/`：环境体检与一键配置（探测 ADB、写 adbPath、检查 iOS 工具链、冲突提醒、复检）。
- `skills/layout-lookin-server/`：自动把 LookinServer 集成进用户 iOS 工程（CocoaPods / SPM 双路径）。

## 非目标

- 不动 Core / web / mac 产品代码；设备页空态不新增 UI 提示。
- 不做 npm 发布物；不改 LICENSE。
- 不自动写 AI 客户端的 MCP 配置（layout-see skill 已覆盖端点发现）。

## 事实源（skill 内容的硬依据）

### Android

- ADB 探测：`repos/core/src/layoutsee_core/adb.py` `find_adb`——settings `adbPath` → `which` → 候选路径（`/opt/local/bin/adb`、`/opt/homebrew/bin/adb`、`/usr/local/bin/adb`、`~/Library/Android/sdk/platform-tools/adb`、`~/Android/Sdk/platform-tools/adb`）。
- `bootstrap.py` 启动时自动回填命中的候选路径；settings 键 `adbPath` 落在 `~/Library/Application Support/LayoutSee/settings.json`，`SettingsStore` 读取时与 DEFAULTS 合并、未知键忽略——外部写最小文件安全（原子写 0600 需对齐 `settings.py:_atomic_write`）。

### iOS

- LayoutSee Core pin **协议版本 7**（`ios/client.py` `SUPPORTED_SERVER_VERSION`），对应 LookinServer **1.1.8 ~ 1.2.8**；1.2.8 为最新（2024-04-06），此后无新版。
- CocoaPods：Swift 项目 `pod 'LookinServer', :subspecs => ['Swift'], :configurations => ['Debug']`；OC 项目去 subspecs；pod 内宏无条件定义，Debug-only 完全靠 `:configurations`；数组名必须与工程 build configuration 精确匹配；subspecs × 多 configuration 组合受限（LookinServer#134）；静态库需 ≥ 1.1.0；< 1.0.6 禁用。
- SPM：`https://github.com/QMUI/LookinServer`，`upToNextMajorVersion + minimumVersion 1.2.8`；Release 安全由包内 `.when(configuration: .debug)` 宏保证；pbxproj 五段结构（packageReferences / XCRemoteSwiftPackageReference section / packageProductDependencies / XCSwiftPackageProductDependency section / PBXBuildFile + Frameworks phase）。
- 连接：真机 47175–47179（usbmux）、模拟器 47164–47169（loopback）；无 Info.plist 配置、无需集成代码；单客户端独占（须退官方 Lookin）；App 后台丢监听需冷启动；iOS 恒只读。

## 交付物结构

两个 skill 均按 `skills/layout-see/` 约定组织：`SKILL.md`（frontmatter = name + description 触发词）+ `README.md` + `VERSION.md` + `references/` + `scripts/`（仅标准库）。

- `layout-env`：`scripts/env_check.py`（`check [--json]` 七项体检 + `set-adb`，exit code 0/1/2/3，`LAYOUTSEE_DATA_DIR` 可重定向演练）；references 的 android-setup / ios-setup。
- `layout-lookin-server`：`scripts/inspect_ios_project.py`（只读摸底，输出 verdict：`recommend-cocoapods` / `recommend-spm` / `cocoapods-integrated` / `spm-integrated` / `possibly-integrated` / `swiftpm-package` / `unknown`）；references 的 cocoapods / spm / troubleshooting。

脚本约束（沿用 workspace 既有约定）：子进程一律 argv 列表（`AdbClient.run` 先例）；网络只碰回环（`mcp_call.py` `_assert_loopback` 模式）；零第三方依赖。

## 文档登记

- 根 README.md / README.en.md：「开始使用」修正过时 iOS 表述并补 LookinServer 前置；「交给 Agent」补两个 skill 与示例 prompt。
- `docs/repo-structure.md`：skills 树与导航补两行。
- `docs/STORY.md`：本 Story 索引行，story 文件 `docs/story/26-11-03-一键环境配置skill.md`。

## 验收标准

1. `env_check.py check` 真机环境跑通，JSON 各键与 SKILL.md 表格一致；`set-adb` 非法路径 exit 3、合法写入 exit 0、保留其余键、0600、App 运行时拒写 exit 2（`LAYOUTSEE_DATA_DIR` 演练）。
2. `inspect_ios_project.py` 对 fixture 正确产出三种 verdict（CocoaPods 已集成含 lock 版本、SPM 已集成含 minimumVersion、空目录 unknown）。
3. skill 同步 `~/.agents/skills/` 后 diff 一致；`npm run lint` 全绿（未动产品代码）。
