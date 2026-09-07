# repos/plugins 说明

## 这个仓库是什么

LayoutSee 随包发行的插件包目录。每个子目录是一个独立插件包，打包时被 PyInstaller 整体塞进 Core 包内的 `layoutsee_core/builtin_plugins`，索引里标 `origin: "builtin"`。用户自己放到 `~/Library/Application Support/LayoutSee/plugins` 的包标 `origin: "local"`，同 id 时 local 覆盖 builtin。

目录里不放构建脚本、不引 npm 依赖：插件页运行在 `sandbox="allow-scripts"` 的 iframe 里，CSP 是 `connect-src 'none'`，只能加载包内静态资源与宿主提供的 `/plugin-runtime.js`。因此插件代码必须是可直接被浏览器执行的 HTML/CSS/JS，没有打包步骤。

当前插件：

| 目录 | id | 宿主 | 作用 |
|------|----|------|------|
| `snapshot-overview/` | `snapshot-overview` | app + web | 内置示例：快照统计 + 声明式组合工具 `capture_then_summarize` |
| `android-logcat/` | `android-logcat` | 仅 app | Android 日志抓取：级别/tag/pid 过滤、暂停继续、清空重抓、自动滚动与换行 |

## 对外提供什么

- `manifest.json`：契约在 `repos/contracts/schemas/plugin/manifest.json`（`schemaVersion: "2.0"`）。入口只能声明式给出（`contributions.workbenchTabs` / `workbenchCards` / `commands` / `mcpTools` / `diagnosticRules`），宿主读清单就能画出入口，代码只在入口被打开时加载。
- `activation` 只允许 `onOpen | onSnapshot | onCommand`，schema 层没有「启动即激活」，插件数量不影响 Core 冷启动。
- 能力只能走 `$u` 桥（`repos/web/public/plugin-runtime.js`），方法白名单在 `repos/web/src/features/plugins/bridgeHost.js`；插件拿不到会话令牌，写操作要用户授权并留 ActionLog（带 `pluginId`）。

## 对内依赖什么

- 路径解析：`repos/core/src/layoutsee_core/bootstrap.py` 的 `builtin_plugins_dir()`（先找包内 `builtin_plugins`，回落本目录；`LAYOUTSEE_BUILTIN_PLUGINS` 可覆盖）。
- 索引与资源托管：`core/plugins.py` + `core/server.py` 的 `/api/v1/plugins/index`、`/plugin-assets/{id}/*`。
- 入口渲染：`repos/web/src/features/plugins/registry.js`（host / devicePlatform 过滤）与 `tabs/PluginsTab.jsx`（卡片流）。

## 怎么加一个插件

1. 新建 `repos/plugins/<id>/manifest.json`，`hosts` 只写真正支持的宿主，`permissions` 只写会用到的；
2. 放入口资源（后缀白名单 `.html .js .mjs .css .json .png .svg .woff2`），页面里用 `<script src="/plugin-runtime.js">` 拿 `$u`；
3. 需要 Core 侧能力时写 `tools.json` / `rules.json`（声明式组合，不能跑第三方 Python）；
4. 验证：`npm run test:contracts`（清单契约与随包插件校验）+ `npm run test:core`（索引、资源托管、宿主声明）；插件页可直接开 `http://127.0.0.1:<port>/plugin-assets/<id>/index.html` 看渲染，但桥能力必须在工作台里连真机验证。

## Build / 测试

无独立构建与测试命令：契约校验挂在 `repos/contracts/tests/contracts.test.mjs`（遍历本目录全部 JSON），端到端托管断言挂在 `repos/core/tests/test_plugin_http.py`。
