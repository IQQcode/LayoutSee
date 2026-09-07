# Story-0831 Web 通用端实现总结

| 属性 | 内容 |
| --- | --- |
| 设计事实源 | [doc.md](./doc.md) |
| 状态 | 编码与非可视化验证完成，待人工真机可视化确认 |
| 分支 | `feature/story-0831-web` |

## 交付结果

| 编号 | 交付物 | 状态 | 落点 |
| --- | --- | --- | --- |
| W1 | 会话注入 + Host/Origin 双校验 | 完成 | `core/server.py`（`_require_local_caller`、`_send_file` 注入、`/api/v1/paths`）、`web/index.html` |
| W2 | `dev:web` 编排 + vite 代理 | 完成 | `scripts/dev-web.mjs`、`web/vite.config.mjs`、根 `package.json` |
| W3 | `HostBridge` 能力清单与降级 | 完成 | `web/app/HostBridge.js`（替代 `ShellBridge.js`）、`SettingsPage`、`PluginsTab`、`AppShell`、`theme.js`、`GlobalErrorBoundary` |
| W4 | 层级三栏交互补齐 | 完成 | `core/selectors.py`（候选加 `kind`）、`ElementTab.jsx`、`DeviceCanvas.jsx`、`WorkbenchPage.jsx`、`app.css` |
| W5 | 包管理 | 完成 | `core/adb.py`（`apps(include_system)`、`clear_app`、`uninstall_app`）、`core/server.py`、`CommonTab.jsx` |
| W6 | 终端 | 完成 | `core/server.py`（`POST /devices/{id}/shell`）、`web/features/workbench/tabs/TerminalTab.jsx`、`api/client.js` |
| W7 | 契约回填 | 完成 | `contracts/openapi/core-v1.yaml`（shell、apps 参数、动作枚举说明、selectors kind、paths、ui-logs、window-size、media/stream） |

## 与设计的偏差

三处按更严格或更贴合既有约定的方式落地，doc.md 未同步修改，以本节为准：

1. **终端审计不落命令原文**。doc.md 写「含完整命令」，实现改为沿用 `audit.py` 既有的 `SENSITIVE_ACTION_TYPES`（本就包含 `device_shell`），只记录字符数与 sha256 前 16 位。命令原文与 stdout 都不落盘，比设计更保守。
2. **卸载对系统应用直接禁用**。按 doc.md 要求，列表里系统应用的卸载按钮 `disabled` 并带 tooltip 说明；Core 侧仍有第二层保护：`pm uninstall` 输出没有 `Success` 就报 `PERMISSION_REQUIRED`。
3. **`--open` 只在带 `--static-dir` 时生效**。Core 不托管首页时没有可打开的页面，避免打开一个 404。

新增了设计未提的两点小改动：

- `repos/web` 补 `test` 脚本，并把 `test:web` 并入根 `test:unit`，让 doc.md 验收表里的 Web 单测真正进门禁。
- 收敛了 vite 配置重复：dev 代理写进原有的 `vite.config.mjs`，删掉过程中多出来的 `vite.config.js`（Vite 会优先取 `.js`，两份并存是隐患）。

## 验证结果

非可视化验证全绿：

```bash
npm run lint          # contracts / web / mac 三份静态检查通过
npm run test:unit     # contracts 7 + mac + web 7 + core 82，全部 OK
npm run contracts:check   # 契约生成物一致：3 个文件
npm --workspace @layoutsee/web run build   # 构建通过，产物无 token 常量（只有占位符字符串）
```

本次新增的 Core 单测：

- `test_browser_host.py`（9 项）— 首页令牌注入、Content-Length 与替换后正文一致、静态资源不被改写、Host/Origin 拒绝矩阵、无 Origin 放行、health 也受保护、`/api/v1/paths`
- `test_device_shell.py`（8 项）— 命令作单个 argv 传入、会话必需、只读拦截、空命令与超长命令拒绝、超时收敛到 60s、256KB 截断、审计只留命令哈希
- `test_package_manager.py`（5 项）— `system` 标记、查询过滤、`pm clear` 成功判定、`Failure` 识别为失败、非法包名在调用 adb 之前被拒

生产形态冒烟（Core `--static-dir repos/web/dist`，无设备）：

- 首页 `<meta name="layoutsee-session">` 内容为本次启动的真实令牌，占位符已消失
- `GET /api/v1/info` 正常返回
- 带 `Origin: http://evil.local` 请求 `/api/v1/devices` 被拒，错误码 `PERMISSION_REQUIRED`

## 未完成 / 待人工确认

- **真机全链路**：Chrome 下「设备列表 → 工作台 → 抓取 → 选节点 → XPath 命中切换 → tap → 终端 → 包管理」需要接真机人工走一遍。
- **降级路径**：Safari 缺失或部分支持 WebCodecs 时落到截图轮询，需人工确认标识清晰。
- **壳内回归**：Electron 壳里令牌仍走 IPC、Core 重启后令牌刷新，单测已覆盖握手金样，端到端仍建议人工确认一次。
- **上游回写**（doc.md 第 10 节列出，本次只做了后两项）：PRD 补「浏览器宿主为一等运行形态」、技术评审 4.3 标注 Origin 白名单实现位置。`INDEX.md` 与 `source/web/{overview,setup,test}.md` 已更新。
- **V0.2 顺延**：安装 APK（需文件上传通道）、颜色取色、命令(Beta)、录制(Beta)。

## 并行改动风险

本 Story 与 plugins Story 并行修改了同一批文件：`core/server.py`、`core/bootstrap.py`、`core/mcp_catalog.py`、`core/errors.py`、`core/audit.py`、`contracts/**`、`web/features/workbench/WorkbenchPage.jsx`。实现期间每次改动前重读文件并保留了对方改动，但合并前建议重点复核这几个文件的 diff，尤其是 `server.py` 的路由分发顺序与 `WorkbenchPage.jsx` 的 Tab 注册。
