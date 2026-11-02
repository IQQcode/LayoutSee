# iOS 接入 Lookin（v22.7.0 第一版）实施计划

> 面向执行者：逐个 Task 实施本计划，步骤用 checkbox (`- [ ]`) 跟踪。

**目标：** 在 Core 内纯 Python 复刻 Lookin 客户端协议，让集成了 LookinServer 的 iOS App 出现在 LayoutSee 并完成与 Android 同构的布局抓取，Web 端可查看。

**架构：** 新增 `layoutsee_core/ios/` 包承担协议栈（usbmuxd 隧道 → PeerTalk 帧 → NSKeyedArchiver → Lookin 请求编排），`IOSDeviceDriver` 对上暴露与 AdbClient 同风格接口；DeviceRegistry 双源轮询、CaptureCoordinator 按 platform 分派；iOS 抓取产出 uiautomator 风格 XML 走既有 `normalize_nodes`，下游 XPath/诊断/摘要零改动。方案事实源：`specs/22_7_ios_lookin/doc.md`。

**技术栈：** Python 3.10+ 纯标准库（socket、struct、plistlib、xml.etree），无新依赖；contracts OpenAPI/JSON Schema + node 生成脚本；web 为纯 JS React（Vite）。

**工作项清单来源：** `specs/22_7_ios_lookin/doc.md`「工作项拆分」章节。

**提交绑定策略：** 提交信息前缀带上工作项编号，例如 `W1: 新增 ios 协议包与诊断脚本`。

## 工作项任务列表

| Task | 工作项编号 | 工作项标题 |
| --- | --- | --- |
| Task 1 | W1 | iOS 协议包与验证工具 |
| Task 2 | W2 | Core 集成（注册表/抓取/路由分平台） |
| Task 3 | W3 | 契约同步（device.json + 生成物） |
| Task 4 | W4 | Web 最小支持 |

---

### Task 1: iOS 协议包与验证工具

## 目标
`repos/core/src/layoutsee_core/ios/` 包可独立完成「枚举设备 → 隧道 → 握手 → 拉层级+属性 → 生成 XML」全链路（真机在场时）；无真机时协议层单测与诊断脚本可独立验证。

## 上下文
Lookin 为 C/S 架构：被测 App 内嵌 LookinServer 1.2.8（协议版本 7），真机上监听设备 loopback 47175–47179；mac 侧经 usbmuxd Connect 到这些端口后，用 PeerTalk 帧协议收发 NSKeyedArchiver 载荷。分层与常量事实源见 doc.md「架构和技术设计」「关键接口与数据结构」；协议源参照 QMUI/LookinServer @develop（MIT）：`Src/Main/Shared/Peertalk/Lookin_PTProtocol.m`（帧头 16 字节 version/type/tag/payloadSize，全部 htonl 大端）、`LookinDefines.h`（请求类型 Ping=200/App=201/Hierarchy=202/HierarchyDetails=203、版本区间 [7,7]、错误码域）、`LookinDisplayItem.h`（subitems/frame/classChainList/attributesGroupList）、`LookinConnectionResponseAttachment.h`（lookinServerVersion/error/appIsInBackground/dataTotalCount/currentDataCount 分批语义）。

## 工作项绑定
- 编号：W1
- 来源：doc.md 工作项拆分章节

## 范围
- 范围内：新建 `ios/` 包全部模块与 `__init__.py`；新建 `tests/test_ios_protocol.py`；新建 `repos/core/scripts/diagnose_lookin.py`。包文件头注明协议事实源与 MIT/GPL 边界。
- 范围外：不改动 devices.py/snapshots.py/server.py/bootstrap.py/errors.py（Task 2 的事）；不做模拟器端口扫描（诊断脚本可选预留 `--emu` 提示未实现，不实现）；不做属性修改类请求（AttrModification/InvokeMethod 不实现）。

## 相关文件
- 可能创建：`repos/core/src/layoutsee_core/ios/__init__.py`、`usbmux.py`、`peertalk.py`、`archiver.py`、`client.py`、`driver.py`
- 可能创建：`repos/core/tests/test_ios_protocol.py`、`repos/core/tests/fixtures/lookin/`（bplist 金样）
- 可能创建：`repos/core/scripts/diagnose_lookin.py`
- 参考：`repos/core/scripts/diagnose_scrcpy.py`（脚本风格）、`repos/core/src/layoutsee_core/adb.py`（客户端类风格：errno 收敛、无拼接 subprocess）、`repos/core/tests/test_session_token.py`（金样测试风格）

## 验收标准
- [ ] `usbmux.py`：`UsbmuxClient.list_devices()` 连接 `/var/run/usbmuxd`，无设备/无 usbmuxd 时返回空列表且不抛未捕获异常；`connect(udid, port)` 发送 plist Connect（PortNumber 大端 u16），Result 非 0 时抛 `IOS_DEVICE_NOT_FOUND` 或 `LOOKIN_APP_NOT_FOUND`（端口拒绝）。
- [ ] `peertalk.py`：`write_frame`/`read_frame` 16 字节大端头往返一致；payloadSize 上限 512MB 防御，流提前 EOF 抛 `LOOKIN_UNAVAILABLE`。
- [ ] `archiver.py`：能解码 `$top/$objects/$class` 结构，支持 NSDictionary/NSArray/NSString/NSNumber/NSData/NSMutableData/NSSet 及未知类骨架（保留 `$class` 类名与键值）；能编码 `LookinConnectionAttachment{dataType, data}`。
- [ ] `client.py`：`ping()` 校验 `7 <= serverVersion <= 7`，区间外抛 `LOOKIN_VERSION_MISMATCH`；`app_info()`/`hierarchy()`/`hierarchy_details()` 正确聚合分批响应（`dataTotalCount/currentDataCount` 累加判定完成），超时（App 0.5s、其余 5s）抛 `OPERATION_TIMEOUT`。
- [ ] `driver.py`：`devices()` 返回 `deviceId="ios-{udid}"、platform="ios"、capabilities=["layout"]、readonly=True`、status=connected；`capture(udid)` 输出 `{"xml", "window_size", "app", "warnings"}`，端口扫描按 47175→47179 顺序、只接受 `appIsInBackground=False` 的 App，全部后台/无响应抛 `LOOKIN_APP_NOT_FOUND`；XML 为 uiautomator 风格 `<hierarchy>`，bounds 为 `frame × screenScale` 取整。
- [ ] `diagnose_lookin.py`：`--list`、`--scan`、`--capture` 三个子命令；无 usbmuxd/无设备时打印明确中文提示退出码 0 或 1（--scan/--capture 无设备为 1），有设备时输出 JSON。

## 测试预期
- 单元测试：`test_ios_protocol.py` 覆盖——帧编解码往返/短读/超限；usbmux plist 消息编解码（用 `socket.socketpair` 本地对拍，不依赖真 usbmuxd）；archiver 编码→解码还原（含嵌套 DisplayItem 树、NSData、中文字符串）；archiver 对一份**手工构造的 bplist 金样 fixture** 解码断言（防编解码同源漂移）；client 的版本区间校验与分批聚合（用 FakeStream 注入预录帧序列）；driver 的 XML 生成（固定 Lookin 树输入 → 断言 XML 字段与 bounds 换算）。
- 集成或运行时验证：`diagnose_lookin.py --list` 在本机（有/无 usbmuxd 皆可运行）。
- 命令：`npm run test:core`（等价 `uv run --project repos/core python -m unittest discover -s repos/core/tests -p 'test_*.py' -v`）
- 预期结果：全部用例通过，既有用例零失败。

## 约束
- 纯标准库，`pyproject.toml` 不加依赖；无 subprocess、无 urllib（Mimosa hook 约束：网络一律纯 socket）。
- 不复制 hughkli/Lookin（GPL-3.0）mac 客户端代码；协议常量与结构注释标明出处为 QMUI/LookinServer（MIT）。
- 错误码名只能用 Task 2 将登记的四个：`IOS_DEVICE_NOT_FOUND`、`LOOKIN_APP_NOT_FOUND`、`LOOKIN_VERSION_MISMATCH`、`LOOKIN_UNAVAILABLE`（本 Task 允许暂时以 `CoreError(code, ...)` 抛出，映射在 Task 2 补齐后自动生效）。

---

### Task 2: Core 集成（注册表/抓取/路由分平台）

## 目标
iOS 设备出现在 `/api/v1/devices`，对 iOS 设备抓取返回与 Android 同构的快照 record，Android 链路行为零变化；iOS 设备的全部写路由被只读门禁拦截。

## 上下文
doc.md「架构和技术设计」与「数据流或调用链」：registry 双源轮询合并（离线标记逻辑复用既有实现 devices.py:115-138）；`CaptureCoordinator._capture`（snapshots.py:248）按 descriptor.platform 分派——Android 走原逻辑不动，iOS 调 `IOSDeviceDriver.capture(udid)` 后把 xml/window_size 送入既有 `normalize_nodes`（snapshots.py:42）生成 nodes/refs，`screenshot=None` 并追加 warning。装配入口 `bootstrap.build_core`（bootstrap.py:40）。

## 工作项绑定
- 编号：W2
- 来源：doc.md 工作项拆分章节

## 范围
- 范围内：devices.py、snapshots.py、bootstrap.py、errors.py、server.py 的分平台处理；新增 `tests/test_ios_capture.py`。
- 范围外：不改 `ios/` 包内部实现（发现缺陷回 Task 1 修）；不改 adb.py；不动 MCP 工具目录（mcp_catalog.py）；不动 web。

## 相关文件
- 可能修改：`repos/core/src/layoutsee_core/devices.py`、`snapshots.py`、`bootstrap.py`、`errors.py`、`server.py`
- 可能创建：`repos/core/tests/test_ios_capture.py`
- 参考：`repos/core/tests/test_device_shell.py`（build_core + Stub 注入模板）、`repos/core/src/layoutsee_core/server.py:277-375`（GET 路由）、`:405-475`（写路由）

## 验收标准
- [ ] errors.py 登记并映射：`IOS_DEVICE_NOT_FOUND`→409、`LOOKIN_APP_NOT_FOUND`→409、`LOOKIN_VERSION_MISMATCH`→426、`LOOKIN_UNAVAILABLE`→503。
- [ ] `DeviceRegistry.__init__` 接受可选 `ios` 数据源并并行轮询（线程内合并结果；adb 失败不影响 iOS 列表，反之亦然；离线/恢复逻辑对两平台一致）。
- [ ] `CaptureCoordinator` 按 `descriptor.platform` 分派；iOS 抓取 record 含 `snapshot.windowSizePx`（screen×scale）、`screenshot=None`、warning 提示「iOS 暂不支持截图，以线框渲染」；nodes/refs/xml/elements 字段与 Android 同构。
- [ ] server.py：iOS 设备访问 `window-size` 返回最新快照缓存的尺寸（无快照时 404 DEVICE_NOT_FOUND 语义维持现状）；`media/capabilities` 对 iOS 返回 `mode="none"`；`current-app`/`apps`/`screenshot`/`logcat*`/`shell`/`actions` 对 iOS 抛 `READ_ONLY_MODE`（403，文案说明 iOS 当前仅支持只读布局抓取）。
- [ ] bootstrap.py 装配 `IOSDeviceDriver` 注入 registry 与 capture；`CoreContext` 增加字段。
- [ ] Android 回归：既有测试全部通过，`refresh()`/`_capture()` 对 android 设备的行为与重构前一致。

## 测试预期
- 单元测试：`test_ios_capture.py` 仿 test_device_shell.py——`build_core` 起真实 server 后注入 StubIOSDriver（预置固定 XML/window_size），断言：`GET /api/v1/devices` 含 ios 条目（platform/capabilities/readonly 字段正确）；`POST /api/v1/devices/{id}/snapshots` 返回同构 record（nodes 含 boundsPx/windowSizePx 正确）；`GET /snapshots/{id}` 可读；对 iOS 调 `actions`/`shell`/`window-size`（无快照时）分别得到 403/404 约定码；StubIOSDeviceDriver 抛 `LOOKIN_APP_NOT_FOUND` 时 HTTP 409。
- 集成或运行时验证：`npm run test:core` 全量。
- 命令：`npm run test:core`
- 预期结果：新旧用例全部通过。

## 约束
- 不改变 `/api/v1/devices` 响应外层结构（`items/lastError/refreshedAt`）。
- registry 轮询周期沿用 `pollIntervalMs`，不为 iOS 单开线程池；usbmux 枚举失败视为「本轮无 iOS 设备」并保留上一轮结果（与 adb 失败同语义）。
- snapshot record 的 `hierarchyAccuracy`/`synchronization` 语义沿用现有取值，不新增枚举。

---

### Task 3: 契约同步（device.json + 生成物）

## 目标
契约事实源接受 platform=ios，三处生成物同步，漂移门禁通过。

## 上下文
doc.md「关键接口与数据结构」：iOS descriptor 沿用现有 Device schema 全部字段；capabilities 复用 `layout`（不下发 screenshot/input/apps）。生成脚本 `repos/contracts/scripts/generate.mjs` 会重建 `generated/` 并覆写 `repos/core/src/layoutsee_core/generated_contracts.py`。

## 工作项绑定
- 编号：W3
- 来源：doc.md 工作项拆分章节

## 范围
- 范围内：`repos/contracts/schemas/device/device.json` 的 platform enum；运行 `npm run contracts:generate`。
- 范围外：不改 capabilities enum、不改 openapi/core-v1.yaml（无新端点）、不动 fixtures/valid|invalid 下现有样例（若其中样例断言 platform 枚举导致契约测试失败，允许为 ios 增补 fixture 并同步测试清单）。

## 相关文件
- 可能修改：`repos/contracts/schemas/device/device.json`
- 可能重新生成：`repos/contracts/generated/typescript/index.ts`、`repos/contracts/generated/python/layoutsee_contracts/models.py`、`repos/core/src/layoutsee_core/generated_contracts.py`（生成物，禁止手改）
- 参考：`repos/contracts/tests/contracts.test.mjs`（7 项契约测试）

## 验收标准
- [ ] `device.json` platform enum 为 `["android","ios"]`。
- [ ] `npm run contracts:generate` 后 `npm run contracts:check` 通过（无漂移）。
- [ ] `npm --workspace @layoutsee/contracts run test`（契约测试）通过。

## 测试预期
- 单元测试：契约测试套件自身。
- 集成或运行时验证：contracts:check 的临时目录重生成比对。
- 命令：`npm run contracts:generate && npm run contracts:check && npm --workspace @layoutsee/contracts run test`
- 预期结果：三条命令退出码均为 0。

## 约束
- 生成物必须由脚本产出，禁止手改；版本号不动（本 Task 不涉及 PRODUCT_VERSION）。

---

### Task 4: Web 最小支持

## 目标
浏览器里：设备页 iOS Tab 列出真实 iOS 设备（含空态集成引导）；进入 iOS 工作台默认快照视图、抓取后显示 wireframe；Android 行为不变。

## 上下文
doc.md「数据流或调用链」第 6 步 + Explore 盘点结论：`DevicesPage` 平台 Tab 骨架在 `PLATFORMS`（DevicesPage.jsx:24-42），`platform !== "android"` 时整块渲染 `PlatformPlaceholder`（:132-137）；`WorkbenchPage.viewMode` 初始恒 `"live"`（:122），插件扩展模型 `devicePlatform` 硬编码 `"android"`（:155）；`DeviceCanvas.liveActive`（DeviceCanvas.jsx:49）不检查 platform，iOS 会误开 scrcpy 流；无 screenshot 元数据时 DeviceCanvas 已自动只画 wireframe（:163 可选链），零改动。

## 工作项绑定
- 编号：W4
- 来源：doc.md 工作项拆分章节

## 范围
- 范围内：DevicesPage.jsx、WorkbenchPage.jsx、DeviceCanvas.jsx 的平台分支；如 android-logcat 插件 manifest 未声明平台，为其补 `devicePlatform: "android"` 声明（schema 允许时）或在前端过滤逻辑中排除。
- 范围外：不动样式 tokens/app.css（wireframe 样式已存在）；不改 api/client.js 端点；不动 MCP/Intelligence/Element Tab 内部实现；不做 iOS 插件。

## 相关文件
- 可能修改：`repos/web/src/features/devices/DevicesPage.jsx`、`repos/web/src/features/workbench/WorkbenchPage.jsx`、`repos/web/src/features/workbench/DeviceCanvas.jsx`、`repos/plugins/android-logcat/manifest.json`
- 参考：`repos/web/src/features/devices/PlatformPlaceholder.jsx`、`repos/web/tests/plugin-registry.test.mjs`（buildExtensionModel 平台过滤测试）

## 验收标准
- [ ] 设备页 iOS Tab：有 iOS 设备时渲染与 Android 相同结构的表格（行内平台列按 `device.platform` 显示 iOS 图标/文案），「控制」可进工作台；无设备时渲染 LookinServer 集成三步引导（pod 集成 Debug 配置 → 真机运行 App → USB 连接），保留「返回 Android」入口。
- [ ] 工作台：iOS 设备 viewMode 初始为 `"snapshot"`（不请求 media/stream）、抓取成功进入快照视图显示 wireframe；`DeviceCanvas.liveActive` 对 `platform !== "android"` 恒 false；common Tab 对 iOS 隐藏（TAB 计算 `platform === "ios" ? ["element","mcp","plugins","intelligence"] : TAB_IDS`）；设备信息栏平台名取自 device.platform；插件扩展模型 devicePlatform 传真实平台（android-logcat 在 iOS 设备不出现或标注不可用）。
- [ ] Android 回归：Android 设备的 live 默认视图、五 Tab、插件行为与改动前一致。

## 测试预期
- 单元测试：若平台 Tab 过滤/TAB 计算提炼为纯函数，在 `repos/web/tests/` 增补 node:test 用例（对齐 workbench-interactions.test.mjs 风格）；无纯函数可提炼时说明理由并以联调代替。
- 集成或运行时验证：`npm run dev:web` 起本地链路（无真机时用 StubIOSDriver 的 Core），人工核对设备页与工作台。
- 命令：`npm run test:web`
- 预期结果：全部通过。

## 约束
- UI 按 `device.platform`/capabilities 驱动，禁止 `isElectron` 式嗅探（HostBridge 既有约定）；文案中文。
