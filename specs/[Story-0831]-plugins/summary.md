# [Story-0831] 插件模块通用接口层 — 实施总结

## 交付范围

按 `doc.md` 的 W1–W6 顺序全部落地：契约层 → Core 清单与资源托管 → Core 侧声明式插件 → 前端扩展模型与挂载 → 能力桥与 SDK → 能力表与内置插件。

## 各层落点

**契约（W1）**
- `repos/contracts/schemas/plugin/`：`manifest.json`（v2.0，`hosts` + `devicePlatforms` 拆分修掉旧 `platforms` 语义冲突）、`manifest-v1.json`（兼容读取）、`index.json`、`bridge.json`（15 项方法白名单）、`core-contribution.json`（声明式工具与诊断规则）
- `schemas/common/error.json` + `core/errors.py`：新增 `PLUGIN_NOT_FOUND(404)`、`PLUGIN_PERMISSION_DENIED(403)`、`PLUGIN_RATE_LIMITED(429)`、`HOST_CAPABILITY_UNAVAILABLE(501)`、`PLUGIN_INCOMPATIBLE(426)`
- `openapi/core-v1.yaml`：`/api/v1/plugins/index`、`/api/v1/plugins/{pluginId}/permissions`、`/plugin-assets/{pluginId}/{assetPath}`

**Core（W2/W3）**
- `plugin_manifest.py`：清单常量、semver 判定、`clean_relative` 路径净化、贡献点归一化
- `plugins.py`：`PluginRegistry` — 构造不触盘、`(路径, mtime_ns, size)` 签名缓存 + `.index.json`、builtin/local 双源与 `overrides` 标记、`resolve_asset`（逃逸/符号链接/后缀三重拒绝）
- `server.py`：索引与兼容列表接口、`/plugin-assets/` 托管（插件专用严格 CSP）、主文档 CSP 放宽到 `frame-src 'self'`
- `plugin_runtime.py` + `mcp_catalog.py`：声明式组合工具解释执行（只能调内置工具、≤6 步）、诊断规则谓词求值、`plugin.{id}.{name}` 独立命名空间，内置目录恒为 12 项
- `audit.py`：写操作审计事件带 `pluginId`

**前端（W4/W5/W6）**
- `features/plugins/registry.js`：`buildExtensionModel` 按 host/devicePlatform 过滤，产出 tabs/cards/commands 与 unavailable 原因
- `features/plugins/PluginSlot.jsx`：激活即挂载、离开即销毁（等价 LRU=1）、8s 超时可重载、快照/选中节点以事件推送
- `features/plugins/bridgeHost.js`：来源校验（`event.source` + opaque origin）、方法白名单、清单声明 + 用户授权双校验、读 20/s 写 2/s 限流
- `public/plugin-runtime.js`：插件侧 `$u` SDK
- `WorkbenchPage`：插件 Tab 与内置 Tab 合并，插件索引在 `requestIdleCallback` 里拉，首屏与工作台首绘路径不发插件请求
- `PluginsTab`：从清单列表升级为入口清单（来源、覆盖关系、激活时机、不可用原因、一键打开）
- `repos/plugins/snapshot-overview/`：随包内置示例插件（含声明式组合工具 `capture_then_summarize`）；插件包统一放 `repos/plugins`，`mac/scripts/package.mjs` 把该目录整体纳入 PyInstaller `--add-data` → 包内 `layoutsee_core/builtin_plugins`

## 与设计文档的三处落地修正

1. 插件 CSP 不能用 `'self'`：sandbox 无 `allow-same-origin` 时文档是 opaque origin，`'self'` 匹配不到任何来源，改为显式回环 origin；两套策略互斥下发而非叠加。
2. `$u` runtime 落在 web 静态产物 `/plugin-runtime.js`，不额外造 `/plugin-assets/__runtime__/` 虚拟路由。
3. 授权状态存宿主前端 `localStorage`，而不是 Core `SettingsStore`——授权是当前宿主用户的决策，壳与浏览器各自独立。

以上均已回写 `doc.md`。

## 验证

- `npm run test:core`：69 通过（新增 26 项，覆盖构造期不扫盘打桩断言、缓存命中不重解析、50 插件冷解析 <150ms / 热命中 <15ms、路径逃逸与符号链接拒绝、engines 不兼容、local 覆盖 builtin、v1 清单升级、插件 CSP 与策略不跨请求泄漏、声明式工具引用替换与断言失败、非内置调用拒绝、诊断规则命中、内置插件端到端）
- `npm run test:contracts`：7 通过（新增「随包内置插件符合契约」）
- `npm run contracts:check`：生成物一致
- `npm run lint`（web + mac）、`vite build`：通过

未做可视化验证：插件 iframe 的真实渲染、授权弹窗与快照事件推送需要连真机后人工确认。

## 已知遗留

- `/api/v1/plugins/{pluginId}/permissions` 在 OpenAPI 已声明，Core 侧尚未实现（当前授权在前端闭环）；若后续要跨宿主同步授权再补。
- `runtime: "sidecar"`（第三方 Python 插件）仅在契约里预留，未实现。
- `$u.fetch` / `$u.shell` 按设计不在 V0.1 开放，需回写 PRD 4.8。

## 后续增量：Android 日志抓取插件（2026-09-03）

第一个真实业务插件落地，同时把插件目录抽成独立模块，验证「新增插件不改宿主代码」这条目标。

**做了什么**
- `repos/plugins/` 成为独立模块（原 `core/src/layoutsee_core/builtin_plugins` 迁出）。`bootstrap.builtin_plugins_dir()` 先找包内 `builtin_plugins`（打包形态）再回落工程目录（开发形态），`LAYOUTSEE_BUILTIN_PLUGINS` 仍可覆盖；打包与契约测试路径同步。
- `repos/plugins/android-logcat/`：`hosts: ["app"]`（按需求本期只做壳内），入口 `workbenchTabs.logcat`。UI 对齐 Android Studio 日志区：过滤表达式 `tag:/-tag:/pid:/level:` + 裸文本、级别下拉、Cc 区分大小写、清空/暂停/重抓/滚到末尾/soft-wrap/导出，点某行即停止自动滚动。
- Core 新增 logcat 能力：`logcat.py` 的 `LogcatHub`（周期 `logcat -d -v threadtime` dump + 重叠锚点对齐 → 带 seq 游标的增量行，锚点对不上置 `dropped`）、`GET /devices/{id}/logcat`（只读，无需会话）、`POST /devices/{id}/logcat/clear`（写：会话 + 只读门禁 + 审计）。
- 桥新增 `device.logcat`（`device.read`）与 `device.logcatClear`（`device.write`），`$u.device.logcat/logcatClear` 同步；写操作请求体带 `pluginId`，ActionLog 可回溯到插件。
- 插件入口改为卡片流：`PluginsTab` 一插件一张圆角卡片，点击进二级页；二级页用 `.plugin-detail` 整块盖住任务 Tab 栏，只留返回栏；插件不再出现在顶部 Tab 栏与控制轨。主题/只读/切设备经新增 `context.changed` 桥事件下发（iframe 读不到宿主 `data-theme`）。

**为什么不给插件开 `$u.device.shell`**：那等于把任意 adb shell 交给插件，安全模型直接失效。改成语义化的只读日志端点，读日志不再被只读模式拦（读本来就不该拦），清空日志才按写操作对待。

**验证**：`npm run test:core` 98 通过（新增 `test_logcat.py` 16 项 + 插件 HTTP 断言 logcat 插件仅 app 且资源可托管）、`npm run test:web` 10 通过（新增 `plugin-registry.test.mjs`：app 宿主可见 / web 宿主进 unavailable）、`npm run test:contracts` 7 通过、`contracts:generate` 无漂移、web lint + build 通过；插件页在真实 Core 下 `/plugin-assets/android-logcat/index.html` 渲染无控制台报错。

**未验证**：真机日志流、授权弹窗、只读模式下清空按钮禁用等需要连设备人工确认（本机当前 `adb devices` 为空）。
