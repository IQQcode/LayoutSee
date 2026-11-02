# iOS 布局抓取接入 MCP 与 Skill 实施计划

> 面向执行者：逐个 Task 实施本计划，步骤用 checkbox (`- [ ]`) 跟踪。

**目标：** LayoutSee Core 的 12 个 MCP 内置工具对 iOS 设备全部可用（读工具正确返回、写工具恒只读拦截），`skills/layout-see` skill 从 Android-only 升级为双平台，并同步到用户级副本。

**架构：** MCP 端点层（`/mcp/{deviceId}/sse|message`）与抓取链路（`snapshots.py _capture_ios` 产出与 Android 同构的 record）已平台无关，本计划只补 `mcp_catalog.py` 中 3 个走 adb 硬编码的工具 handler 的平台分派，行为口径与 `server.py` 既有 HTTP iOS 分支（`_ios_window_size` / `_ios_foreground`）对齐。Skill 层不改工具语义，只补双端触发词、server 名形态与 iOS 平台差异语义（恒只读、无 density、ObjC 类名、extras/Lookin 分组、ivar、203 底图降级、单客户端独占）。

**技术栈：** Python 3（`http.server` + unittest，无第三方依赖）；Markdown skill 文档；Node 根 workspace 脚本（`npm run test:core` / `npm run lint`）。

**工作项清单来源：** 本文件下方「工作项清单」（think 阶段已与用户确认：单 skill 双平台、MCP 对齐 HTTP 分支 + 快照回落、同步用户级副本）。

**提交绑定策略：** 提交信息前缀带上工作项编号，例如 `W1: MCP 工具层 iOS 平台分派`。

## 工作项清单

| 编号 | 端 | 标题 | 内容描述 |
| --- | --- | --- | --- |
| W1 | 服务端（Core） | MCP 12 工具 iOS 适配 | `get_device_info` / `get_current_app` / `get_screenshot` 三个 handler 增加 iOS 平台分派，与 HTTP 分支口径一致；补 MCP iOS 单测；contracts 查证 |
| W2 | SDK（Skill） | layout-see skill 双平台化 | SKILL.md 与全部 references 双端化、iOS 平台差异节、`mcp_call.py` 文案、README、同步用户级副本 |

## 工作项任务列表

| Task | 工作项编号 | 工作项标题 |
| --- | --- | --- |
| Task 1 | W1 | MCP 12 工具 iOS 适配 |
| Task 2 | W2 | layout-see skill 双平台化 |

---

### Task 1: MCP 12 工具 iOS 适配

## 目标

iOS 设备经 MCP 端点（`POST /mcp/ios-<udid>/message`）调用 9 个读工具返回正确结果，3 个写工具（tap/swipe/input_text）返回 `READ_ONLY_MODE`；Android 路径行为不变。

## 上下文

- 抓取链路已就绪：`repos/core/src/layoutsee_core/snapshots.py` 的 `CaptureCoordinator._capture_ios()` 产出与 Android 同构的 record（snapshot 含 snapshotId/foreground/windowSizePx/nodes/extras 回填，png 为 203 渲染图或 None，elements/element_to_key/refs 齐全），`capture_layout` / `get_layout` / `query_xpath` / `get_layout_summary` / `diagnose_layout` / `find_element` / 带 snapshotId 的 `get_screenshot` 已天然支持 iOS。
- 仅 `repos/core/src/layoutsee_core/mcp_catalog.py` 的三个 handler 硬编码走 adb：`_tool_get_device_info`（platform 写死 "android"、density/orientation 走 adb）、`_tool_get_current_app`（`adb.current_app`）、`_tool_get_screenshot` 实时分支（`adb.screenshot`）。
- 行为口径对齐 `server.py` 既有 iOS HTTP 分支：`_ios_window_size`（最新快照读，无快照 `SNAPSHOT_STALE`）、`_ios_foreground`（最新快照 foreground，无快照 `LOOKIN_APP_NOT_FOUND`）。
- iOS 恒只读已生效：`devices.py DeviceRegistry.is_readonly` 对 iOS 恒 True，`mcp_catalog.py _write_guarded` 已拦，本任务只需单测验证，不改写工具代码。
- contracts 已查证（2026-10-31）：`repos/contracts/schemas/mcp/tool-catalog.json` 只约束工具结构（name/kind/description/inputSchema），无平台字段，无需回填；跑 `contracts:check` 确认无漂移即可。

## 工作项绑定

- 编号：W1
- 来源：本计划「工作项清单」W1 行

## 范围

- 范围内：`mcp_catalog.py` 三个读工具 handler 的平台分派；`tests/test_ios_capture.py` 新增 MCP 用例；跑门禁命令确认无回归
- 范围外：写工具（tap/swipe/input_text）逻辑；iOS 驱动（`ios/` 包）；snapshots.py 抓取链路；web 前端；contracts schema 内容修改；server.py HTTP 分支

## 相关文件

- 修改：`repos/core/src/layoutsee_core/mcp_catalog.py`
- 修改：`repos/core/tests/test_ios_capture.py`
- 参考（口径事实源）：`repos/core/src/layoutsee_core/server.py`（`_ios_window_size` 约 596-607 行、`_ios_foreground` 约 609-619 行）、`repos/core/src/layoutsee_core/errors.py`（错误码）、`repos/core/src/layoutsee_core/devices.py`（`is_readonly` iOS 恒 True）
- 参考（测试基建）：`repos/core/tests/test_ios_capture.py` 的 `StubIOSDriver`（duck-typing，capture 返回 window_size 1170×2532、app=LookinDemo/com.qmui.lookindemo、extras、无 screenshot 键）、`StubAdb`；现有测试通过 `HTTPConnection` 直打 `/mcp/<deviceId>/message` JSON-RPC

## 具体行为定义

1. **`get_device_info`**：读 `registry.device(device_id)` 的 platform 分派。
   - Android 分支：现状不变（platform="android"、adb window_size/density/orientation）。
   - iOS 分支返回：`{"deviceId", "platform": "ios", "serial", "model", "status", "readonly": True, "windowSizePx": <最新快照 windowSizePx>, "density": None, "orientation": "landscape" if width>height else "portrait"}`。最新快照从 `store.latest_for(device_id)` 取；无快照抛 `CoreError("SNAPSHOT_STALE", "iOS 设备窗口尺寸随首次抓取返回，请先调用 capture_layout。")`（消息与 server.py `_ios_window_size` 同义，无需 status 参数）。
   - dispatcher 需要访问 `store` 与 `registry`（构造函数已注入两者）。
2. **`get_current_app`**：iOS 从 `store.latest_for(device_id)` 读 `snapshot["foreground"]` 返回 dict；无快照抛 `CoreError("LOOKIN_APP_NOT_FOUND", "iOS 前台 App 信息随首次抓取返回，请先调用 capture_layout。")`。Android 分支现状不变。
3. **`get_screenshot`**：
   - 有 `snapshotId` 参数：现状不变（通用 record png）。
   - 无 `snapshotId` 且 platform 为 ios：取最新快照 record；record 为 None 抛 `SNAPSHOT_STALE`；record 的 png 为 None（真机渲染图拉取失败降级线框）抛 `CoreError("MEDIA_UNAVAILABLE", "iOS 无实时截图链路且本次快照没有渲染底图，请重新 capture_layout。", retryable=True)`；有 png 返回 base64。
   - 无 `snapshotId` 且 platform 为 android：现状不变（`adb.screenshot`）。
4. 错误码全部沿用 `errors.py` 既有码（SNAPSHOT_STALE / LOOKIN_APP_NOT_FOUND / MEDIA_UNAVAILABLE），不新造错误码。

## 验收标准

- [ ] iOS 设备 `get_device_info` 返回 platform="ios"、windowSizePx 来自最新快照、density=null、orientation 按快照宽高推断、readonly=true
- [ ] iOS 设备无快照时 `get_device_info` 返回 SNAPSHOT_STALE、`get_current_app` 返回 LOOKIN_APP_NOT_FOUND、`get_screenshot` 返回 SNAPSHOT_STALE
- [ ] iOS `capture_layout` 成功后 `get_current_app` 返回 `{packageName: "com.qmui.lookindemo", appName: "LookinDemo"}`，`capture_layout` 返回 foreground/windowSizePx/nodeCount/synchronization 与 Android 同构
- [ ] iOS 快照无 png 时 `get_screenshot` 返回 MEDIA_UNAVAILABLE（retryable）
- [ ] iOS `tap`/`swipe`/`input_text` 均返回 READ_ONLY_MODE，审计有 blocked-readonly 记录
- [ ] Android 既有行为不变（StubAdb 路径：get_device_info 返回 density=420、get_current_app 走 adb、get_screenshot 实时走 adb.screenshot）
- [ ] `npm run test:core` 全绿；`npm run lint` 通过；`npm run contracts:check` 无漂移

## 测试预期

- 单元测试（新增用例写入 `tests/test_ios_capture.py`，复用 `IOSCaptureTest` 的 build_core/StubIOSDriver 基建，通过 `HTTPConnection` POST `/mcp/ios-udid-1/message` 发 JSON-RPC `tools/call`）：
  1. iOS get_device_info（capture 后）：platform=ios、windowSizePx={"width":1170,"height":2532}、density None、orientation portrait、readonly True
  2. iOS get_device_info（capture 前）：JSON-RPC error 含 SNAPSHOT_STALE
  3. iOS get_current_app（capture 前/后）：LOOKIN_APP_NOT_FOUND / packageName=com.qmui.lookindemo
  4. iOS get_screenshot（capture 后，StubIOSDriver 无 screenshot 键 → png 为 None）：MEDIA_UNAVAILABLE
  5. iOS tap / swipe / input_text：READ_ONLY_MODE
  6. Android get_device_info / get_current_app / get_screenshot 回归（走 StubAdb，值与现状一致）
- 集成或运行时验证：无真机时以单测为准；有模拟器环境时可用 `python3 skills/layout-see/scripts/mcp_call.py --devices` 与 `capture_layout` 抽查（最终可视化确认由人负责）
- 命令：`npm run test:core`（根目录，等价 `cd repos/core && python -m unittest discover`）；`npm run lint`；`npm run contracts:check`
- 预期结果：三条命令全部退出码 0，无失败用例

## 约束

- 遵循 `mcp_catalog.py` 现有 handler 风格（小函数、f-string 中文报错、直接 dict 返回），不引入新依赖、不加抽象层（不建 PlatformAdapter 之类的类）
- Mimosa hook 约束：不新增 subprocess/urllib 动态调用；本任务改动不涉及网络与子进程
- 提交信息：`W1: MCP 工具层 iOS 平台分派（device_info/current_app/screenshot）`，中文描述
- 提交前 `git status --short -uall` 确认只含本任务文件（工作区有用户改动 `.v2c/plugin_root`，不得纳入提交）

---

### Task 2: layout-see skill 双平台化

## 目标

`skills/layout-see/` 成为 Android + iOS 双平台布局感知 skill：触发词覆盖双端、数据源形态补全 iOS server 名、iOS 平台差异语义完整可查、脚本与 README 去 Android 中心化，并同步到 `~/.agents/skills/layout-see/`。

## 上下文

- W1 完成后 MCP 12 工具对 iOS 的实际行为：9 个读工具可用（get_device_info 无 density、get_screenshot 实时=快照底图回落）、3 个写工具恒 `READ_ONLY_MODE`。skill 必须与该口径逐条一致，不虚构能力。
- MCP 端点与 server 名已平台无关：端点 `/mcp/{deviceId}/sse|message`；server 名 = `layoutsee-{deviceId}`，即 `layoutsee-android-<serial>`、`layoutsee-ios-<udid>`、`layoutsee-ios-sim-<port>`（模拟器deviceId 见 `ios/driver.py IOS_SIMULATOR_PREFIX`）。
- iOS 语义事实源：`specs/22_7_ios_lookin/`（doc.md/summary.md）、根 `INDEX.md` ios 行、`repos/core/src/layoutsee_core/snapshots.py _capture_ios` 注释。关键差异：恒只读（Lookin 无 tap/输入注入）；无独立 density；foreground.packageName= bundleId；className 是 ObjC 类名（UIView/UIButton 等）；节点带 extras（Lookin 属性分组 + ivar 名，web 端 ElementTab 已按分组渲染）；`driver.bounds` 是父链累加的窗口绝对坐标（item.frame 相对父视图）；203 底图失败时模拟器回退 simctl、真机降级线框（快照 png 为 None）；Lookin 单客户端独占（与官方 Lookin 分时）；App 后台丢监听需冷启动；AllAttrGroups(210) 只认 layer oid。
- 用户级副本 `/Users/jiazihui/.agents/skills/layout-see/` 是全局会话实际加载的版本，改完 workspace 后整目录同步（内容级对齐，含删除工作区已不存在的文件）。

## 工作项绑定

- 编号：W2
- 来源：本计划「工作项清单」W2 行

## 范围

- 范围内：`skills/layout-see/` 全部文件的双端化改造；`~/.agents/skills/layout-see/` 同步
- 范围外：Core 代码、web 前端、contracts、其它 skill、`docs/`、工作区 AGENTS.md/INDEX.md

## 相关文件

- 修改：`skills/layout-see/SKILL.md`（frontmatter description、触发条件表、数据源节、工具地图、新增「平台差异」节、精度边界）
- 修改：`skills/layout-see/references/mcp-tools.md`（端点/device_id 双平台、工具表 iOS 备注、错误码补 LOOKIN_APP_NOT_FOUND、tap ref 用法标 iOS 不可用）
- 修改：`skills/layout-see/references/mcp-direct-fallback.md`（device_id 三形态、示例补 iOS、`adb devices` 文案改 Core 设备列表）
- 修改：`skills/layout-see/references/viewnode-schema.md`（补 iOS 快照示例：className=UIView/UIButton、extras、density null）
- 修改：`skills/layout-see/references/runtime-view-workflow.md`（resource-id 措辞双端化：iOS 定位证据用 ivar/自定义类名/文案）
- 核查按需修改：`skills/layout-see/references/diagnosis-playbook.md`（证据表达是否 Android 中心化）
- 修改：`skills/layout-see/scripts/mcp_call.py`（仅 docstring 与报错文案，如「请用 adb devices 确认」改为指向 Core 设备列表；不新增参数与功能）
- 修改：`skills/layout-see/README.md`（定位从「Android 运行时视图感知工具」改双端）、`skills/layout-see/VERSION.md`（按需 bump）
- 参考（事实源）：`specs/22_7_ios_lookin/doc.md`、`specs/22_7_ios_lookin/summary.md`、`skills/layout-see/references/attrFormat.js 相关说明见根 INDEX.md`（extras 格式化事实源 LookinAttrIdentifiers）

## 验收标准

- [ ] SKILL.md frontmatter description 同时含 Android 与 iOS 触发词，不再出现「不用于 iOS 视图调试」类排除表述
- [ ] 数据源节列出三种 device_id 形态与对应 server 名，端点写法与 Core 实际一致
- [ ] 平台差异表逐条与 Core 行为一致：iOS 写工具不可用（READ_ONLY_MODE）、无 density、foreground.packageName=bundleId、className 为 ObjC 类名、extras/Lookin 分组属性与 ivar、boundsPx 绝对坐标 vs item.frame 相对父视图、get_screenshot 实时=快照底图回落、203 底图降级线框、单客户端独占、App 后台丢监听需冷启动
- [ ] mcp-tools.md 错误码表补 LOOKIN_APP_NOT_FOUND；tap 的 ref 用法节明确 iOS 不可用
- [ ] 全目录无「仅支持 Android」类过时表述（`grep -rn "仅 Android\|不用于 iOS\|Android-only" skills/layout-see/` 为空；描述 Android 事实的普通表述不算）
- [ ] `python3 -m py_compile skills/layout-see/scripts/mcp_call.py` 通过
- [ ] `~/.agents/skills/layout-see/` 与 workspace 版本 diff 为空（`diff -r skills/layout-see ~/.agents/skills/layout-see`）

## 测试预期

- 命令：`python3 -m py_compile skills/layout-see/scripts/mcp_call.py`；预期退出码 0
- 运行时验证（Core 运行且有设备时）：`python3 skills/layout-see/scripts/mcp_call.py --devices` 输出的 iOS 设备含 `deviceId: ios-...`；`python3 skills/layout-see/scripts/mcp_call.py capture_layout` 对 iOS 设备可返回快照摘要（无设备时以单测与文档核对为准）
- 文档核对：对验收标准逐条人工核对；grep 确认无过时表述残留
- 预期结果：脚本可运行、文档与 Core 行为零冲突、双份目录内容一致

## 约束

- 事实源优先：iOS 差异表述以 Task 1 实际实现 + specs/22_7_ios_lookin + INDEX.md 为准，不引入文档未沉淀的新能力声明
- 不虚构数据：iOS 写工具一律写「不可用」，get_screenshot 写「实时调用回落最新快照底图」
- 文档风格遵循 skill 现有密度（表格化、中文、避免长段落）
- 提交信息：`W2: layout-see skill 双平台化（iOS 接入）`，中文描述；用户级副本 `~/.agents/` 不在 git 仓库内，不参与提交
