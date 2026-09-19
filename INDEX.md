# 代码模块索引

快速定位各工程模块。行数后的说明为模块当前职责；改代码前先看本索引与对应 `source/<repo>/{overview,setup,test}.md`。

最后更新：2026-09-18。行数会漂移，职责说明以代码为准。

模块一览：`repos/core`（Python Core）、`repos/web`（React 前端）、`repos/mac`（Electron 壳）、`repos/contracts`（契约事实源）、`repos/plugins`（随包插件包）。

## repos/core — Python 本地 Core（HTTP 服务 + 设备驱动 + 算法）

启动方式：`uv run --project repos/core python -m layoutsee_core --nonce <64hex> [--static-dir <web dist>] [--data-dir <dir>] [--port-start 11663]`。端口从 `DEFAULT_PORT_START`（`server.py`，当前 11663）起最多尝试 10 个，绑定后输出一行 READY JSON。

浏览器宿主：Core 托管 `index.html` 时把本次会话令牌替换进 `<meta name="layoutsee-session">`（占位符 `__LAYOUTSEE_SESSION__`），因此浏览器直接打开 READY 行里的 URL 即可用全部写能力。`/api/**` 与 `/mcp/**` 一律校验 Host（必须回环 + 本端口）与 Origin（存在时必须同源，缺失放行），拦 DNS rebinding 与同机跨源写。

### src/layoutsee_core/

| 模块 | 约行数 | 职责 | 关键点 |
|---|---:|---|---|
| `server.py` | 800 | HTTP 路由与请求处理（`http.server` + ThreadingHTTPServer，非 FastAPI） | 所有 API 路由在此；`_handle` 统一排空请求体（keep-alive 污染教训见 bugs.md 二轮）；`do_OPTIONS` 204；`_require_local_caller` Host/Origin 双校验；`_send_file` 对 index.html 注入会话令牌（先替换再算 Content-Length）；媒体流 `/devices/{id}/media/stream`（chunked）；`/api/v1/ui-logs`、`/api/v1/paths`；终端 `POST /devices/{id}/shell`（命令整串单 argv、只读全禁、256KB 截断、超时上限 60s）；日志 `GET /devices/{id}/logcat`（只读、无需会话）与 `POST /devices/{id}/logcat/clear`（写：会话 + 只读门禁 + 审计）；插件 `/api/v1/plugins/index` 与 `/plugin-assets/{id}/*`（**插件 CSP 用显式回环 origin，不能用 `'self'`**，两套策略靠 `_csp_override` 每请求重置互斥下发）；每请求 stderr 访问日志 `[request] METHOD path -> status`；会话令牌 `X-LayoutSee-Session` = HMAC(nonce, "layoutsee-ui-v1") |
| `media.py` | 390 | scrcpy 实时投屏：ScrcpySession + MediaHub | ADB wire 协议（socket 直连 5037，无子进程——Mimosa hook 约束）；推 jar → `shell:` 服务拉 server → `localabstract:scrcpy` 隧道；帧格式 `[pts u64][len u32][payload]`，pts bit63=config；`i-frame-interval=2` 短 GOP；订阅队列 30 帧丢旧保实时；`reap_idle` 回收无观众会话 |
| `snapshots.py` | 320 | 原子抓取：CaptureCoordinator + SnapshotStore + normalize_nodes | dump XML → 截图 → 前后上下文比对（context_changed）；节点上限 3000/深度 128；store 每设备留 3 份、TTL 600s；ref 令牌 = HMAC(snapshotId) 前 10 hex |
| `adb.py` | 300 | AdbClient：全部 adb 交互唯一入口 | `run()` argv 列表 + shell=False；`find_adb` 候选路径探测（MacPorts/Homebrew/SDK）；`window_size/density/orientation/current_app/apps/screenshot/dump_xml/action`；`logcat_dump`（`-d -v threadtime -t N`）与 `logcat_clear`（部分机型清空成功仍返回非 0，不据此报错）；`apps(serial, query, include_system)` 用两次 `pm list packages` 对比标记 `system`；`clear_app`/`uninstall_app` 校验包名字符集且必须在输出里看到 `Success` 才算成功 |
| `mcp_catalog.py` | 220 | MCP 12 工具目录 + ToolDispatcher | tools/list 运行时生成；写工具统一走 gate/audit；`plugin.{id}.{tool}` 由插件声明式贡献派生 |
| `plugins.py` / `plugin_manifest.py` / `plugin_runtime.py` | ~500 | 插件索引（懒扫盘 + 签名缓存 + 资源解析）/ 清单归一化 / 声明式工具与诊断规则执行 | 构造函数不触盘，冷启动与插件数无关；`resolve_asset` 拒逃逸与符号链接；插件不执行第三方 Python |
| `logcat.py` | 130 | LogcatHub：周期 dump + 重叠锚点对齐 → 带 seq 游标的增量日志 | 不开常驻 `adb logcat` 子进程（全部 adb 调用收敛在 `AdbClient.run`）；锚点对不上置 `dropped`，UI 提示丢日志；`clear` 重置游标与缓冲 |
| `devices.py` | 190 | DeviceRegistry（5s 轮询枚举、offline 标记）+ DeviceGate（每设备串行锁，5s 超时 DEVICE_BUSY） | `serial_for()` 是取序列号唯一入口；readonly 双层（设备级 + 全局默认） |
| `diagnostics.py` | 190 | 六类布局诊断（overlap/occlusion/out_of_bounds/small_touch_target/text_truncation/invisible_interactive） | 纯函数 `diagnose(record, snapshotId)` |
| `bootstrap.py` | ~100 | 装配工厂 `build_core(nonce, static_dir, data_dir, port_start)` | 组装全部服务 + MediaHub + LogcatHub + PluginRegistry + UiLogStore + 媒体回收线程；`builtin_plugins_dir()` 先找包内 `builtin_plugins`（打包形态）再回落 `repos/plugins`（开发形态），`LAYOUTSEE_BUILTIN_PLUGINS` 可覆盖；CoreContext dataclass 在 server.py |
| `audit.py` | ~80 | ActionLog JSONL（requested/result 记录，fsync） | `SENSITIVE_ACTION_TYPES`（`input_text`、`device_shell`）只记长度与 sha256 前 16 位，命令原文与 stdout 不落盘；`source=plugin` 时事件带 `pluginId` |
| `settings.py` | 110 | SettingsStore 原子 JSON 持久化 | `UPDATABLE_KEYS` 白名单；`SYSTEM_KEYS`（schemaVersion）静默忽略——UI 全量回传不报错 |
| `__main__.py` | 45 | CLI 入口：参数解析、nonce 校验、READY 输出、SIGTERM 优雅退出 | |
| `summary.py` | 140 | 语义摘要（确定性，CJK 计权，≤1200 tokens 目标） | 已知欠账：密集页 omittedInteractive>0 |
| `finder.py` | 120 | find_element 词法/结构检索（固定权重） | |
| `xpath.py` / `selectors.py` | ~200 | XPath 查询（elementpath，512 字符上限）与选择器生成（5 类候选） | 查询只针对快照 XML，不重新 dump |
| `uilogs.py` | ~60 | 前端日志落盘 `logs/ui-YYYY-MM-DD.log`，保留 7 天 | 单行制表符分隔 |
| `errors.py` | 80 | CoreError + 错误码→HTTP 状态映射表 | 稳定错误码都在这 |
| `contracts.py` / `generated_contracts.py` | — | CoreInfo 模型 / 契约生成的 Python 类型（禁止手改） | |

### tests/（`npm run test:core` = unittest discover）

- `test_routing_fixes.py` — 回归：OPTIONS 204、`snapshots/latest`/`media/capabilities` 三级路由、快照详情路由、**keep-alive body 残留不污染下一请求**（真机 501 教训）
- `test_browser_host.py` — 浏览器宿主：首页令牌注入与 Content-Length、静态资源不被改写、Host/Origin 拒绝矩阵、`/api/v1/paths`
- `test_device_shell.py` — 终端：单 argv 传参、会话必需、只读拦截、命令长度、超时收敛到 60s、256KB 截断、审计只留命令哈希
- `test_package_manager.py` — 包管理：`system` 标记、查询过滤、`pm clear` 成功判定、`Failure` 识别、非法包名前置拒绝
- `test_session_token.py` — Node/Python HMAC 金样一致
- `test_locking_regression.py` — 非重入锁死锁回归（线程 join 超时断言）
- `test_diagnostics_settings.py` — 六类诊断 + 设置白名单 + schemaVersion 忽略
- `test_logcat.py` — logcat：threadtime 解析与堆栈续行、重叠对齐只回新行、缓冲滚过置 dropped、清空重置游标；端点只读/会话/审计 pluginId
- `test_plugins.py` / `test_plugin_http.py` / `test_plugin_declarative.py` — 插件索引缓存与逃逸拒绝、索引接口与两套 CSP、声明式组合工具与诊断规则贡献
- `test_snapshot_normalize.py` / `test_xpath.py` / `test_summary_selectors.py` / `test_adb_discovery.py` / `test_fake_core.py`（fake_core/server.py 假 Core，场景 DSL）

### scripts/

- `diagnose_scrcpy.py` / `repro_session.py` — 真机 scrcpy 链路手动排查工具（推 jar、开隧道、逐帧打印）

## repos/web — React 前端（Vite 构建产物由 Core 同源托管）

`npm --workspace @layoutsee/web run build` → dist 复制进 Core static。纯 JS（无 TS），ESM。

两种宿主同一套产物：Electron 壳与浏览器。浏览器联调走根目录 `npm run dev:web`（`scripts/dev-web.mjs` 先起 Core 拿 READY，再派生令牌注入 vite dev，`vite.config.mjs` 把 `/api` `/mcp` `/health` 代理到 Core 并摘掉 Origin）。

### src/

| 文件 | 职责 | 关键点 |
|---|---|---|
| `main.jsx` | 入口 + 路由：`/devices`、`/group`、`/settings`、`/devices/:id/workbench/:tab` | 启动时 `wireLogging()` |
| `api/client.js` | fetch 封装 + api 对象（全部端点） | 令牌注入 `X-LayoutSee-Session`；**网络层日志**：非 2xx 记 `[LayoutSee][网络]`，`/api/v1/ui-logs` 豁免防递归 |
| `api/logger.js` | 统一 Tag 日志 `[LayoutSee][Tab名]` | `uiLog/uiLogApi/LogTags`；1.5s 批量上报；上报通道由 LoggingBridge 注入（避免循环依赖） |
| `media/scrcpyStream.js` | ScrcpyViewer：拉流 → 解析 → WebCodecs 解码 → canvas | **avcC description 长度必须精确**（多 1 字节 Chromium 零输出且无报错）；丢帧后等关键帧；解码器错误自愈；pts 取低 48 位 |
| `app/AppShell.jsx` | 侧边导航 + 标题栏 + KernelBanner | 左侧导航与标题栏齿轮用 `MorphGlyph`，激活态 morph（设备→充电、群控→宫格勾、设置→设置2） |
| `app/HostBridge.js` | 宿主抽象：`kind`（shell / browser）+ `can` 能力清单 + 会话初始化 | 壳走 IPC 会话，浏览器读 `<meta name="layoutsee-session">`（dev 下回落 `VITE_LAYOUTSEE_SESSION`）；UI 按 `can` 渲染，禁止 `isElectron` 式嗅探；两者都没有令牌时进入只读观察模式并出横幅 |
| `app/LoggingBridge.js` / `theme.js` / `GlobalErrorBoundary.jsx` | 日志接线 / 主题（data-theme + 原生同步）/ 错误边界 | |
| `components/MorphIcons.jsx` | **左侧图标系统**：morphicons（MIT）+ Lucide 图标数据，`glyphs` 集中导出 | 换 prop 即弹簧变形，无需 from/to 或 key；`MorphGlyph` 统一 19px / 线宽 2 / `reducedMotion="user"`（跟随系统减弱动效）；**新增图标只改这个文件**；图标必须是描边中心线集（Lucide/Tabler/Heroicons outline），Phosphor 填充型不可用 |
| `components/ui.jsx` | Button/IconButton/Banner/Dialog/Toast(useToast)/CopyButton/EmptyState/Spinner | toast 2.4s 自动消失；`Button.icon` 与 `IconButton.icon` 都**自动区分**「图标组件」与「Lucide 图标数据（数组）」——传数据给期望组件的 prop 会抛 React #130 白屏，已踩过两次 |
| `components/ResizeHandle.jsx` | 可访问分隔条（方向键/Shift/Home/End/双击复位） | |
| `features/workbench/WorkbenchPage.jsx` | 工作台编排：设备轮询、抓取、只读、viewMode 状态机、控制轨、底部状态栏 | **TAB_IDS 顺序**（常用-元素查看-MCP-插件-布局智能；终端已收拢进插件页，`/workbench/terminal` 路由保留并复用 `.plugin-detail` 二级页外壳）；`selectNode` 是替换式红色高亮唯一入口（XPath/诊断高亮保留）；设备区宽度自适应 + 手动拖动后记忆；状态栏的分辨率取 `window-size`、Core 版本取 `/api/v1/info`，各取一次；**控制轨图标全走 `glyphs` + `MorphGlyph`**：冻结/只读/审查为状态 morph，音量/旋转/抓取为 `pulseIcon` 一次性 morph，Tab 图标按选中态 morph，抓取三态=相机→旋转加载→对勾（`capturing` / `captureDone`） |
| `features/workbench/DeviceCanvas.jsx` | 设备画面：live（scrcpy）/ snapshot（布局查看）/ 截图降级三态 | **点击坐标按设备物理分辨率换算**（`window-size` 端点），不是推流分辨率；布局查看=点选命中不注入 tap；live 模式零边框满幅；`onPointerInfo` 以 60ms 节流上报坐标给状态栏 |
| `features/workbench/tabs/ElementTab.jsx` | 元素查看：属性面板 + 层级树 + XPath + 选择器 + 导出 | 树渲染递归 **必须传 nodeKey 数组**（传对象数组=树空 bug 根源）；快照加载默认全展开；属性行 resource-id 置顶；Minimal Light/Dark 语法高亮（`--code-*` 变量）；`XPath by [id\|text\|class\|自定义]` 按 Core 返回的 `kind` 回填；多命中渲染序号 chip（>200 折叠为跳转输入框） |
| `tabs/CommonTab.jsx` | 当前应用/启停 + 包管理（搜索、系统应用开关、启动、停止、清除数据、卸载） | 启动表单预填前台应用（用户已输入不覆盖）；高危动作走统一二次确认弹窗；只读模式下写操作全禁 |
| `tabs/TerminalTab.jsx` | 终端：自由输入 adb shell 命令 | 入口在插件页终端卡片，二级页复用 `.plugin-detail` 外壳（返回栏「< 插件」）；历史 100 条按设备隔离存 localStorage，上下键翻历史、Ctrl/Cmd+L 清屏；高危前缀（rm / pm uninstall / reboot / settings put …）二次确认，只是提醒不是安全边界；超时 15/30/60s 可选 |
| `tabs/McpTab.jsx` / `tabs/IntelligenceTab.jsx` / `tabs/PluginsTab.jsx` | MCP 配置与工具列表 / 摘要+诊断 / 插件卡片流 | `PluginsTab` 是插件与内置工具的入口承载：终端卡片固定在卡片流首位（空插件目录时也在），一插件一张圆角卡片，点卡片进二级页（`WorkbenchPage` 用 `.plugin-detail` 整块盖住任务 Tab 栏，只留返回栏），插件不再往顶部 Tab 栏与控制轨塞入口 |
| `features/plugins/registry.js` / `bridgeHost.js` / `PluginSlot.jsx` | 插件入口模型 / 桥宿主端 / iframe 生命周期 | Core 索引不做 host/devicePlatform 过滤，过滤在 `buildExtensionModel`；桥来源校验是 `event.source === frame.contentWindow && event.origin === "null"`（sandbox 无 allow-same-origin）；宿主**不下发**会话令牌；方法白名单 + 清单声明 + 用户授权 + 限流四层；主题/只读/切设备靠 `context.changed` 事件下发 |
| `public/plugin-runtime.js` | 插件侧 SDK `$u`（随宿主发布，不进插件包） | `$u.device.logcat/logcatClear`、`$u.snapshot.*`、`$u.host.can/saveFile/copyText`、`$u.storage`、`$u.ui`；只接受 `event.source === window.parent` 的回包 |
| `public/favicon.ico` / `favicon-*.png` / `apple-touch-icon-180x180.png` / `layoutsee-icon-192.png` | 站点图标与品牌 logo | 引用点：`index.html`（favicon 链接）、`AppShell.jsx` / `WorkbenchPage.jsx` 的 `.brand-mark`；切图源头在 `docs/designs/logo/exports/` |
| `features/devices/DevicesPage.jsx` | 设备表格 + 平台 Tab（Android / iOS / HarmonyOS） | 操作列 sticky right 12px 同宽 150px 中心对齐；**行底色必须用不透明的 `--ls-color-row-bg(-hover)`**，粘性列 `background-color: inherit`——父子各画一层半透明 hover 会叠出灰条 |
| `features/devices/PlatformPlaceholder.jsx` | iOS / HarmonyOS 未开放平台占位面板 | 逐词模糊入场（BlurText 风格，`step` 控制错峰：标题 90ms、长段落 26ms）+ `background-clip: text` 光泽扫过（ShinyText 风格）；参考 reactbits 但**纯 CSS 实现，不引 motion**；reduced-motion 下降级静态 |
| `features/settings/SettingsPage.jsx` | 设置页 | `save(patch)` **只发补丁**，不回传整个对象 |
| `features/group-preview/GroupPreviewPage.jsx` | 群控预览（截图轮询，未接 scrcpy） | |

### styles/

- `tokens.css` — 全部 `--ls-*` 变量（标题栏 48px、侧栏 188px、控制轨 68px）+ `[data-theme="dark"]` 覆盖
- `app.css` — 应用骨架与全部组件样式；**全局 reset 在文件头**（body margin 0，勿删——删了窗口四周出现 8px 白边）；`node-overlay.wireframe/.selected`（红=选中）

### tests/

- `scrcpy-stream.test.mjs` — 解码器纯函数单测（AnnexB 分割 / avcc / avcC 精确长度）
- `workbench-interactions.test.mjs` — 终端历史环形缓冲与高危命令识别、XPath 命中序号收敛（用源码切片执行 JSX 文件里的纯函数）
- `plugin-registry.test.mjs` — `buildExtensionModel`：app 宿主可见、只声明 app 的插件在 web 宿主进 unavailable、设备平台不匹配也留原因

跑法：`npm run test:web`（等价 `cd repos/web && node --test tests/*.test.mjs`），已并入 `npm run test:unit`

## repos/mac — Electron 壳（进程守护 + 安全边界，无业务逻辑）

`npm --workspace @layoutsee/mac run package:mac` 产 DMG（默认本机架构）；`package:mac:all` 一次出 arm64 + x64 两套并归档到 `release/mac-arm64/`、`release/mac-x64/`（DMG 与解包 .app 同目录）。系统要求 macOS ≥ 13.0（Electron 44 下限，`electron-builder.yml` 钉死），Intel 装 `mac-x64/`、Apple Silicon 装 `mac-arm64/`。

### src/

| 文件 | 职责 | 关键点 |
|---|---|---|
| `main/index.mjs` | 主进程：窗口（1000×720, min 940×640, trafficLight {18,16}）、白名单 IPC、菜单、导航策略 | IPC：`layout:export`（保存对话框）、`adb:choose`、`logs:open` 等，全部 `assertTrustedFrame` |
| `main/kernel-supervisor.mjs` | Core 生命周期：nonce 生成、spawn、READY 解析、`/api/v1/info` 校验、健康检查、重启预算（25s 超时重试一次） | 只认「本次启动的 Core」（pid+nonce） |
| `main/logging.mjs` | 按天日志 `logs/YYYY-MM-DD-{shell,core}.log` | Core stderr 由此收集 |
| `preload/index.cjs` | `contextBridge` 白名单暴露 | 新 IPC 必须同时加 main handler + 这里 + ShellBridge |
| `shared/handshake.mjs` | 跨语言握手金样（版本矩阵 + 令牌推导） | Node 侧与 Python `server.derive_session_token` 必须一致 |
| `bootstrap/index.html` | 内置启动/错误页（不依赖 Core） | |

### scripts/

- `package.mjs` — 打包链（`--arch arm64|x64|all`，缺省本机架构）：web build → 按 arch 构建 PyInstaller onedir（arm64 走 uv 环境；x64 在 arm64 构建机用 python-build-standalone x86_64 解释器经 Rosetta 产出，缓存 `mac/build/python-x64/`，`PBS_MIRROR` 换源；**`--add-data` 打入 scrcpy jar 与 `repos/plugins` → 包内 `layoutsee_core/builtin_plugins`**）→ 资源暂存 → manifest（含 scrcpy 版本/哈希/许可证）→ electron-builder DMG（arch 由 CLI 下发，配置里不固定）。网络波动时用 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/` 前缀重试
- `assets/LayoutSee-1024.png` — 应用图标唯一事实源（白底圆角方版，切图取自 `docs/designs/logo/exports/2026-09-04-white-macos/`）；`build/` 下 iconset/icns 均为打包时再生产物，勿手改；bootstrap 启动页 logo 以 data URI 内嵌在 `src/bootstrap/index.html`（透明底 M，该页 CSP 只放行 `img-src data:`）
- `build.mjs` / `lint.mjs` / `after-pack.cjs`

### tests/

- `handshake.test.mjs` / `kernel-supervisor.test.mjs`（`npm --workspace @layoutsee/mac run test`）

## repos/contracts — OpenAPI/JSON Schema 单一事实源

- `openapi/core-v1.yaml` — HTTP API 定义（scrcpy 流、ui-logs、window-size、paths、shell、logcat 读取与清空、插件索引与资源托管均已回填）
- `schemas/` — common（error/info）、snapshot、websocket（media-v1.md 线格式文档）、mcp、plugin（manifest v2 / manifest-v1 兼容 / index / bridge / core-contribution）、test
- `fixtures/valid|invalid/` — 契约测试样例；`generated/typescript/` 与 `generated/python/` — 生成物禁止手改（`contracts:check` 是漂移门禁）
- `scripts/` — `generate.mjs` / `check-generated.mjs`（漂移门禁）/ `lib.mjs`
- `tests/contracts.test.mjs` — 7 项（含「随包内置插件的清单与声明式工具符合契约」，遍历 `repos/plugins` 下全部 JSON）

## repos/plugins — 随包插件包（无构建步骤）

每个子目录一个插件包，打包时整体进 Core 包内 `layoutsee_core/builtin_plugins`（`mac/scripts/package.mjs` 的 `--add-data`），开发态由 `bootstrap.builtin_plugins_dir()` 回落到本目录。详见 [source/plugins/overview.md](source/plugins/overview.md)。

| 目录 | id | 宿主 | 说明 |
|---|---|---|---|
| `snapshot-overview/` | `snapshot-overview` | app + web | 内置示例：快照统计 + 声明式组合工具 `capture_then_summarize`（`tools.json`） |
| `android-logcat/` | `android-logcat` | **仅 app** | Android 日志抓取：AS 风格过滤表达式（`tag:` / `-tag:` / `pid:` / `level:` / 裸文本）、级别下拉、暂停/继续、清空重抓、点行停滚、soft-wrap、导出；日志经 `$u.device.logcat` 增量拉取，清空经 `$u.device.logcatClear`（只读模式下按钮禁用） |

插件页运行在 `sandbox="allow-scripts"` 的 iframe 且 `connect-src 'none'`：不能内联 `<script>`、不能自行发请求，主题只能靠桥事件同步，所以每个插件自带一份 `--ls-*` 取值的 CSS 变量副本。

## 跨工程速查

| 要改什么 | 去哪 |
|---|---|
| 加/改 HTTP API | `core/server.py` 路由 → `contracts/openapi` 回填 → `web/api/client.js` |
| 加新 IPC | `mac/src/main/index.mjs` → `mac/src/preload/index.cjs` → `web/app/HostBridge.js`（同时给 `can` 加能力位与浏览器降级） |
| 新前端页面/Tab | `web/main.jsx` 路由 → `features/<x>/` → 工作台 Tab 需同步 `WorkbenchPage.TAB_IDS` |
| 加一个插件 | 新建 `repos/plugins/<id>/manifest.json` + 入口资源即可（无需改宿主代码）；需要新桥能力时才动 `web/features/plugins/bridgeHost.js` + `web/public/plugin-runtime.js` + `contracts/schemas/plugin/bridge.json` |
| 调整主题/颜色 | `web/styles/tokens.css`（`--ls-*`）+ `app.css` 的 `--code-*`（层级树代码色） |
| 排查用户问题 | `~/Library/Application Support/LayoutSee/logs/`：`ui-*.log`（前端，统一 Tag）+ `*-core.log`（含 `[request]` 访问日志） |
| 打包发版 | 根目录 `npm run build:all && npm run package:mac:all`（含 verify:artifacts 门禁；只要单架构用 `package:mac` / `package:mac:x64`） |
| 浏览器里联调 | 根目录 `npm run dev:web`，打开 `http://127.0.0.1:4173`；生产形态是 Core `--static-dir <web dist>` 后开 READY 行的 URL |

## 已知坑速查（详见 specs/[Story-0827]-mac-app/{bugs,ux-feedback}.md）

1. keep-alive：任何带 body 的请求必须排空，否则下一请求解析成 `{}GET` → 501（server.py `_drain_request_body` 已兜底）
2. WebCodecs：avcC description 长度精确，多余字节=零输出无报错
3. 点击坐标：设备物理分辨率 ≠ 推流分辨率（max_size 缩放）
4. 层级树递归：只接受 nodeKey 数组
5. Mimosa hook：Bash 写文件、subprocess 拼接、urllib 动态 URL 会被拦；新代码子进程调用收敛到 `AdbClient`，网络用纯 socket 协议实现
6. 浏览器只支持 loopback：局域网 IP 既不可达（Core 只 bind 127.0.0.1），也会丢 secure context（`crypto.randomUUID`、`navigator.clipboard`、WebCodecs 都依赖它）
7. 首页注入令牌后必须按替换后的字节长度写 `Content-Length`，否则浏览器截断首页
8. 插件 iframe 的 CSP 不能写 `'self'`：`sandbox="allow-scripts"`（无 `allow-same-origin`）下文档 origin 是 opaque，`'self'` 序列化成 `null` 匹配不到任何来源，脚本会被自己的策略拦掉——必须写显式回环 origin，且主文档与插件两套策略互斥下发（`_csp_override` 每请求重置，勿叠加）
9. 插件页不能内联 `<script>`、`connect-src 'none'` 不能自行发请求；插件拿不到宿主 `data-theme`，主题只能靠 `context.changed` 桥事件同步
10. 产品版本号必须是 **3 段 semver**（当前 `22.6.1`）：electron-builder 用 `semver.valid(version, loose)` 校验 package.json，4 段（如 `22.6.1.0`）直接抛 `Invalid version` 导致 DMG 打不出来；macOS 的 `CFBundleShortVersionString` 同样只允许 1–3 段。改产品版本时这些点必须同步，漏一个就出不一致或功能降级：4 个 `package.json` + `package-lock.json`（含 `@layoutsee/contracts` 的依赖 pin，只改 package.json 会让 `npm ci` 失配）、`core/pyproject.toml`、`PRODUCT_VERSION` 与 `__version__`、契约 `schemas/common/info.json` 的 `const` 与 `compatibility/versions.json`（改完跑 `contracts:generate` 重生成，生成物禁止手改）、mac `handshake.mjs` 的 VERSION 金样（与 Core READY 行强校验，不一致壳直接拒绝启动）、web `SettingsPage` 里的兼容判定字面量，以及**内置插件 manifest 的 `engines.layoutsee`**——区间上界写死会在改版本后失配，插件被整体判为「版本不兼容」
