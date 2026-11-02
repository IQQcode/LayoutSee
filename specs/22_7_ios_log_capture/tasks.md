# iOS 日志抓取（syslog）实施计划

> 面向执行者：逐个 Task 实施本计划，步骤用 checkbox (`- [ ]`) 跟踪。

**目标：** iOS 真机与模拟器经 `/devices/{id}/logcat` 端点增量读取日志（与 Android 同形），配套新增内置插件 `ios-logcat` 提供 AS 风格过滤抓取。

**架构：** Core 侧新增 `ios/lockdown.py`（lockdown 握手 + StartService `com.apple.syslog_relay`）与 `ios/syslog.py`（vis 解码、真机行解析、模拟器 JSON 提取、SyslogHub 持续流读取线程）；`server.py` 的 `_read_logcat`/`_clear_logcat` 按 device platform 分派；模拟器走 `SimctlClient` 扩展的 `log stream --style json`。条目形状与 Android 同构（`tag`=进程名），端点、桥 `$u.device.logcat`、契约、bridgeHost 全部不动。

**技术栈：** Python 3 标准库（socket/plistlib/ssl/unittest，零第三方依赖）；插件为原生 HTML/CSS/JS（iframe，无构建步骤）。

**工作项清单来源：** [doc.md 工作项拆分章节](./doc.md)。

**提交绑定策略：** 提交信息前缀带上工作项编号，例如 `W1: Core iOS 日志链路（lockdown + SyslogHub + server 分派）`。

## 工作项任务列表

| Task | 工作项编号 | 工作项标题 |
| --- | --- | --- |
| Task 1 | W1 | Core iOS 日志链路（lockdown + SyslogHub + server 分派） |
| Task 2 | W2 | ios-logcat 插件 + 文档回填 |

---

### Task 1: Core iOS 日志链路（lockdown + SyslogHub + server 分派）

## 目标

iOS 真机与模拟器设备经 `GET /api/v1/devices/{id}/logcat` 返回与 Android 同形的增量日志（`{deviceId, lines, cursor, dropped, reset, buffered}`，条目含 `time/pid/tid/level/tag/message/continuation/seq`，`tag`=进程名）；Android 链路行为零变化。

## 上下文

- 方案事实源：[doc.md](./doc.md)。核心差异：iOS 无「事后 dump」，改为每设备一条持续流读取线程（懒启动、断流自愈、环形缓冲 4000 条、seq 游标单调）。
- 真机链路：`UsbmuxClient`（`ios/usbmux.py`，已有 `connect/list_devices` 与 `socket_factory` 注入）新开隧道连 lockdown 62078 → lockdown plist 协议（**4 字节大端长度** + binary plist，区别于 usbmux 16 字节头）→ `QueryType` → `ReadPairRecord`（usbmuxd 消息，`PairRecordID`=UDID）→ `StartSession(HostID)`（响应 `EnableSessionBypass=false` 时对 lockdown 通道用配对证书 TLS）→ `StartService("com.apple.syslog_relay")` → 取响应 `Port`（host 序，直接传 `UsbmuxClient.connect`）与 `EnableServiceSSL`（true 则服务通道 TLS，用配对记录 `HostCertificate/HostPrivateKey`）→ usbmux connect 新隧道 → 裸流按 `\n\x00` 分行 → vis(3) 解码 → 行解析。
- 模拟器链路：`SimctlClient` 扩展——`booted_udids()` 恰好一台时，spawn `/usr/bin/xcrun simctl spawn <udid> log stream --style json --level debug`（argv 列表、shell=False、UDID 过规范 UUID 形态正则校验）；stdout 逐字节累积，顶层 JSON 对象用深度计数 + 字符串感知提取；仅 `eventType=="logEvent"` 入列；`messageType` 映射级别 Default/Info→I、Debug→D、Error→E、Fault→F（本机实测样本：`processImagePath` 取 basename、`processID`、`threadID`、`timestamp`、`eventMessage`）。
- 真机行格式（idevicesyslog.c 解析逻辑）：前 16 字符为 `MMM DD HH:MM:SS ` 时间戳 → 设备名 → 进程`[PID]`（可带 `(image)` 后缀）→ `<Notice>:/<Info>:/<Warning>:/<Error>:/<Debug>:` 或其他 → 消息；短于 16 字符或不匹配 → 上一条续行（`continuation: true`）。级别映射 Notice/Info→I、Warning→W、Error→E、Debug→D、其余→I。
- vis(3) 解码：还原 `\M-x`（高位字节）、`\M^X`、`\ddd`（八进制，值落在可显示/UTF-8 高位段才还原）与 `\\`；控制字符转义保留原样（防终端控制序列注入）。中文日志必经此步。
- iOS clear 语义 = 本地缓冲重置 + 流重连（不触碰设备状态）。`server.py` `_clear_logcat` 对 iOS 的分派放在只读拦截**之前**（iOS 恒只读铁律针对设备注入/修改，本地缓冲清空不属于设备写），照常写审计 `logcat_clear`（allowed）。
- 错误码复用：配对缺失/StartService 被拒/流中断 → `LOOKIN_UNAVAILABLE`；多台 booted 模拟器 → `CORE_UNAVAILABLE`（消息提示仅保留一台）；不新造错误码。
- 装配：`bootstrap.py` 新增 `syslog=SyslogHub(SyslogRelayClient(usbmux), simctl)`，`server.py CoreContext` 增字段（参照 `logcat: Any = field(default=None)` 模式）。

## 工作项绑定

- 编号：W1
- 来源：doc.md 工作项拆分章节 W1 行

## 范围

- 范围内：`repos/core/src/layoutsee_core/ios/lockdown.py`（新增）、`repos/core/src/layoutsee_core/ios/syslog.py`（新增）、`repos/core/src/layoutsee_core/ios/simctl.py`（扩展 `log_stream`）、`repos/core/src/layoutsee_core/server.py`（`_read_logcat`/`_clear_logcat` 分派 + CoreContext `syslog` 字段）、`repos/core/src/layoutsee_core/bootstrap.py`（装配）、`repos/core/tests/test_ios_syslog.py`（新增）、`repos/core/tests/test_ios_capture.py`（补 server 分派用例）
- 范围外：`logcat.py`、`adb.py`、`ios/usbmux.py`、`ios/driver.py`、`snapshots.py`、web 前端、插件包、contracts schema、`mcp_catalog.py`、layout-see skill

## 相关文件

- 新增：`repos/core/src/layoutsee_core/ios/lockdown.py`
- 新增：`repos/core/src/layoutsee_core/ios/syslog.py`
- 修改：`repos/core/src/layoutsee_core/ios/simctl.py`（新增 `log_stream(udid)` 启动子进程并返回 Popen；argv 校验逻辑同文件既有范式）
- 修改：`repos/core/src/layoutsee_core/server.py`（`_read_logcat`/`_clear_logcat` platform 分派；CoreContext 加 `syslog` 字段）
- 修改：`repos/core/src/layoutsee_core/bootstrap.py`（构造 `SyslogHub` 注入 CoreContext）
- 新增：`repos/core/tests/test_ios_syslog.py`
- 修改：`repos/core/tests/test_ios_capture.py`（新增 logcat 分派用例）
- 参考（口径事实源）：`repos/core/src/layoutsee_core/logcat.py`（条目字段与 read/clear 返回形状）、`repos/core/src/layoutsee_core/ios/usbmux.py`（隧道与 socket_factory 注入）、`repos/core/src/layoutsee_core/devices.py`（serial_for/readonly）、`repos/core/tests/test_ios_capture.py`（build_core/StubIOSDriver 测试基建）

## 验收标准

- [x] `ios/lockdown.py` 提供 `start_service(udid, "com.apple.syslog_relay") -> int`（端口），内部完成 QueryType→ReadPairRecord→StartSession→StartService 握手；`EnableServiceSSL=true` 时对服务通道做 TLS；无配对记录抛 `CoreError("LOOKIN_UNAVAILABLE", ...)` 且消息含「请先用 Xcode/Finder 配对设备」
- [x] `ios/syslog.py` 的 `decode_vis` 能还原 `\M-*`/八进制转义为 UTF-8 中文，控制字符转义保留原样
- [x] `parse_relay_line`：标准行产出同构条目；不匹配/短行产出 `continuation=true` 续行；未知级别映射 "I"
- [x] 模拟器顶层 JSON 对象提取器：对 eventMessage 含 `},{` 与花括号的文本样本不串条目；`eventType!="logEvent"` 被过滤；messageType 映射级别正确
- [x] `SyslogHub.read` 支持 `after` 游标增量、`limit` 截断（上限 1000）、`dropped`（缓冲滚过）、`reset`（客户端游标超前）、`buffered`；`clear` 重置游标与缓冲并重连流
- [x] 模拟器 `read`：多台 booted 抛 `CORE_UNAVAILABLE`；UDID 不符合规范 UUID 形态（`^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$`，review 修正由原 36 位宽泛校验收紧）时不启动子进程
- [x] server：iOS 设备 `GET /logcat` 走 SyslogHub（stub 验证）、Android 设备仍走 LogcatHub（既有单测全绿）；iOS `POST /logcat/clear` 在只读（iOS 恒只读）下仍能执行本地清空并写入 `logcat_clear` allowed 审计
- [x] `npm run test:core` 全绿；`npm run lint` 通过；`npm run contracts:check` 无漂移

## 测试预期

- 单元测试（`test_ios_syslog.py`，全部零硬件依赖）：
  1. `decode_vis`：`b"\\M-p\\M-^C\\M->\\M-\\":..."` 类高位转义还原为中文；`\\^A` 控制转义保留；`\\\\` → `\`
  2. `parse_relay_line`：`"Nov  1 00:07:32 iPhone LookinDemo[1234] <Notice>: 你好"` → `{tag:"LookinDemo", pid:1234, level:"I", ...}`；`"    at com.foo.Bar(...)"` 跟在上一条后 → continuation 续行
  3. 模拟器提取：构造含 `"eventMessage": "x }, { y"` 的对象串 → 两条不串；`activityCreateEvent` 过滤；`messageType:"Error"` → "E"
  4. `SyslogHub`（stub 流迭代器）：首读返回既有行、after 增量、缓冲滚过 dropped、after 超前 reset、clear 后游标归零
  5. lockdown 握手（stub socket_factory 按序返回脚本化响应）：断言请求序列含 QueryType/ReadPairRecord/StartSession/StartService；StartService 拒绝 → LOOKIN_UNAVAILABLE
- server 分派用例（`test_ios_capture.py` 新增）：`ios-udid-1` 设备 GET `/api/v1/devices/ios-udid-1/logcat` 返回 200 且 lines 非空（注入 stub SyslogHub）；`GET /api/v1/devices/android-serial-1/logcat` 行为与 `test_logcat.py` 口径一致
- 命令：根目录 `npm run test:core`（等价 `cd repos/core && python -m unittest discover`）、`npm run lint`、`npm run contracts:check`
- 预期结果：三条命令退出码 0，无失败用例；Android 既有用例零改动通过

## 约束

- 零第三方依赖：socket/plistlib/ssl/re/unittest 全标准库；不建抽象层（不搞 PlatformLogAdapter 类），沿用 logcat.py 的小函数 + dataclass 风格
- 全部 adb 以外子进程收敛到 `SimctlClient`；argv 列表化、shell=False、UDID 正则校验
- `ios/usbmux.py` 只复用不修改；若确实缺能力（如 ReadPairRecord 消息封装），在 `ios/lockdown.py` 内实现，usbmux.py 的既有函数签名不动
- 文件头 docstring 注明协议事实源（libimobiledevice `idevicesyslog.c` / pymobiledevice3 `syslog.py` MIT / Apple lockdown 惯例），遵循 `ios/usbmux.py` 现有注释密度
- Mimosa hook：无动态 URL；TLS 用标准库 ssl 模块 + 配对证书内存构造
- 提交信息：`W1: Core iOS 日志链路（lockdown + SyslogHub + server 分派）`，中文描述
- 提交前 `git status --short -uall` 确认只含本任务文件（`.v2c/plugin_root` 与 `specs/22_7_ios_log_capture/` 之外的既有未跟踪文件不得纳入）

---

### Task 2: ios-logcat 插件 + 文档回填

## 目标

`repos/plugins/ios-logcat/` 成为可用的内置插件：iOS 设备工作台出现「日志抓取」卡片，打开后增量抓取、AS 风格过滤、暂停继续、清空显示、导出全部可用；`INDEX.md` 与 `source/plugins/overview.md` 登记完成。

## 上下文

- W1 交付的条目形状：`{time, pid, tid, level, tag(=进程名), message, continuation, seq}`；`dropped/reset/cursor` 语义与 Android 相同。iOS 恒只读 → `context.readonly` 恒 true → 写操作按钮（本插件只有「清空设备日志」类）按 android-logcat 惯例禁用；新增「清空显示」纯前端按钮（`resetBuffer`，保留游标）不受只读限制。
- 过滤表达式在 Android 基础上 iOS 化：`tag:` 语义改为进程名匹配但**键名保留 `tag:` 与新增 `process:`/`proc:` 别名**（三者等价），`pid:`、`level:`、`message:`/裸文本（含 `-` 反选）保持一致；级别下拉为 D/I/W/E/F（iOS 无 V），`LEVEL_ORDER` 用 iOS 序（D=0,I=1,W=2,E=3,F=4）。
- 插件运行环境约束（INDEX.md 已知坑 8/9）：iframe `sandbox="allow-scripts"`、`connect-src 'none'` → 不能内联 `<script>`、不能自行发请求、全部能力走 `$u` 桥；自带 `--ls-*` CSS 变量副本；主题靠 `context.changed` 桥事件。
- manifest 要点：`schemaVersion "2.0"`、`id: "ios-logcat"`、`hosts: ["app"]`、`devicePlatforms: ["ios"]`、`activation: "onOpen"`、`runtime: "iframe"`、`permissions: ["device.read", "storage.local", "host.integration"]`（无 device.write——不调 logcatClear）、`contributions.workbenchTabs` 一项（icon 复用 "terminal"）。
- 空态/提示文案需覆盖系统限制：日志 `<private>` 脱敏说明、dropped 提示、真机需已配对提示。

## 工作项绑定

- 编号：W2
- 来源：doc.md 工作项拆分章节 W2 行

## 范围

- 范围内：`repos/plugins/ios-logcat/` 全部文件；根 `INDEX.md` 的 repos/plugins 表与 `source/plugins/overview.md` 当前插件表各加一行
- 范围外：Core 代码（含 bridgeHost/plugin-runtime）、`android-logcat` 插件、contracts schema、layout-see skill、docs/

## 相关文件

- 新增：`repos/plugins/ios-logcat/manifest.json`
- 新增：`repos/plugins/ios-logcat/index.html`（结构与 `repos/plugins/android-logcat/index.html` 同构：工具条 + 状态栏 + 日志区 + 空态）
- 新增：`repos/plugins/ios-logcat/app.js`（以 `repos/plugins/android-logcat/app.js` 为基线改造：过滤别名、iOS 级别序、清空显示、`<private>` 文案）
- 新增：`repos/plugins/ios-logcat/style.css`（以 android-logcat/style.css 为基线，自带 `--ls-*` 变量副本，级别色对应 iOS 序）
- 修改：根 `INDEX.md`（repos/plugins 表新增 `ios-logcat` 行）
- 修改：`source/plugins/overview.md`（当前插件表新增一行）
- 参考（口径事实源）：`repos/plugins/android-logcat/`（四件套全量参考）、`repos/contracts/schemas/plugin/manifest.json`（清单契约）、`repos/web/src/features/plugins/registry.js`（devicePlatform 过滤行为）

## 验收标准

- [x] `manifest.json` 通过契约校验（`npm run test:contracts` 全绿，含「随包内置插件清单与声明式工具符合契约」遍历用例）
- [x] `permissions` 不含 `device.write`；代码中无 `$u.device.logcatClear` 调用
- [x] `app.js` 的 `parseQuery`：`tag:`、`process:`、`proc:` 等价作用于 `entry.tag`；`pid:` 精确匹配 `entry.pid`；`level:` 单字符映射 iOS 序；裸文本与 `-文本` 正反选
- [x] 级别下拉仅 D/I/W/E/F，选择后按 `LEVEL_ORDER` 阈值过滤；`lvl-D/I/W/E/F` 行样式与 iOS 级别色一致
- [x] 「清空显示」按钮在任何只读状态下可用且只清前端缓冲（不发请求）；「暂停/继续」「点行停滚」「soft-wrap」「导出」行为与 android-logcat 一致
- [x] 空态与提示文案含 `<private>` 脱敏说明与真机配对指引；dropped 提示与 android-logcat 同义
- [x] `INDEX.md` 与 `source/plugins/overview.md` 各新增 `ios-logcat` 登记行（含「仅 app」「iOS 日志抓取」描述）
- [x] `npm run test:core`、`npm run lint`、`npm run test:web` 全绿

## 测试预期

- 命令：根目录 `npm run test:contracts`、`npm run test:core`、`npm run lint`、`npm run test:web`
- 预期结果：全部退出码 0
- 运行时验证（W1 已就绪时）：Core 运行 + 模拟器 booted（本机 UDID 3249070E-B6EE-48BC-9674-E3C93E1C91CB）→ 浏览器开 `http://127.0.0.1:<port>/plugin-assets/ios-logcat/index.html` 可渲染；工作台选中 iOS 模拟器设备 → 插件卡片出现 → 打开后日志滚动、`process:` 过滤生效；真机联调（USB + 已配对测试机）验证中文日志可读（最终可视化确认由人负责）
- 无设备/无 Core 时：以契约测试与代码核对为准，不谎称联调通过

## 约束

- 插件页面结构、类名、交互尽量与 android-logcat 对齐（diff 可读性优先），仅 iOS 差异处偏离并加注释说明
- 不内联 `<script>`、不引外部请求、不新增桥能力（现有 `$u.device.logcat / $u.storage / $u.host.saveFile / $u.ui.toast / $u.on` 足够）
- 文档登记只加行不改既有行
- 提交信息：`W2: ios-logcat 插件（iOS 日志过滤抓取）+ 文档登记`，中文描述
