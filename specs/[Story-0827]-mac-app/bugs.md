# Story-0827 mac app Bug 修复记录

修复时间：2026-08-29（四轮迭代）。涉及构建：`repos/mac/release/LayoutSee-0.1.0-arm64.dmg`（**以最新一次打包为准**，未签名本地候选包）。

> 用户需要在退出当前运行中的 LayoutSee 后，重新安装该 DMG 验证。

---

## 四轮（2026-08-29 午后）：布局树终极修复 + 视觉对齐 UIAutoDev/ZCode

### 1.【重点】布局树不展示——真正的根因终于定位

前三轮一直没修好，本轮用 headless Chrome 加载真实应用 + 真机 83 节点快照，在 DOM 里复现并锁定：

- 根节点 `aria-expanded="true"`、展开箭头存在，但子节点完全不在 DOM —— 排除了数据、状态、CSS 问题；
- 递归渲染 `renderTree(children)` **传入的是节点对象数组**，而函数签名期望 **nodeKey 数组**，`byKey.get(节点对象)` 全部返回 undefined → 每个子节点渲染成 null。顶层调用 `renderTree(rootNodes.map(n => n.nodeKey))` 显式做过映射，所以根永远可见、子树永远为空——**该 bug 自第一版起就存在**；
- 修复：递归改为 `renderTree(children.map((child) => child.nodeKey))`；
- headless 验证：修复前 treeitem=1，修复后 **treeitem=83**。

> 排查方法论沉淀：这类「逻辑模拟正确但 UI 不对」的问题，尽早把真实应用跑到 headless 浏览器里直接断言 DOM，比反复读代码猜快得多。

### 2. UI 层级改为代码风格 + Minimal Light/Dark 主题（对齐 ZCode）

- 树行渲染为语法高亮 XML 片段：`<android.widget.RelativeLayout resource-id="com.baidu.tieba:id/xxx" text="...">`；
- 配色遵循 Minimal 双主题（浅色：标签红/属性蓝/值绿；深色对应提亮），通过 `--code-*` CSS 变量跟随 `data-theme` 自动切换；
- 可点击节点追加 `clickable` 橙色标记；保留点选联动、展开折叠、过滤与 hover 全部交互。

### 3. 布局查看线框视觉对齐 UIAutoDev

此前每个线框叠加 4% 蓝色填充，83 个叠加后画面被蓝蒙层盖住。修复：线框只保留 1px 品牌色边界 + 半像素白描边（深浅画面都清晰），无填充；选中节点仍以品牌色高亮。

### 4. 小窗自适应

设备管理表格 7 列最小宽度合计约 900px，940px 小窗下「操作」列被裁掉。修复：`.table-card` 改横向滚动（`overflow-x: auto`）+ `.device-table min-width: 780px`，小窗下操作列可滚动到而不再截断。

### 验证

- headless Chrome DOM 断言：83 行树、前 3 行 XML 语法文本正确、`--code-*` 主题规则注入；
- 全量单测（Core 34 / 契约 5 / 壳 8 / Web 4）+ lint + verify:artifacts 全绿。

---

## 三轮（2026-08-29 午）：元素查看交互重构 + scrcpy 体验对齐

用户复测反馈 5 项：布局树抓到但看不到内容、交互模式混乱（对齐 UIAutoDev）、缺布局导出、默认窗口偏大、scrcpy 延迟/花屏/热区错乱。日志确认抓取链路已全部 200，属前端交互与投屏体验问题。

### 1. 布局树不展示

根因：层级树默认全部折叠（`expanded` 初始为空 Set），抓取后只显示一行根节点，用户以为没有内容。
修复：快照加载后默认展开整棵树（`setExpanded(所有 nodeKey)`），点选节点的祖先链展开逻辑保留。

### 2. 交互重构：实时投屏 ⇄ 布局查看 双模式（对齐 UIAutoDev）

- 新增 `viewMode` 状态机（`live` / `snapshot`），DeviceCanvas 双渲染路径：
  - **live（默认）**：scrcpy 实时画面，点击/滑动/滚轮注入设备；
  - **snapshot（布局查看）**：点击「抓取 UI 快照」后自动切入——展示快照截图 + 全节点线框叠加（上限 1200 个可见节点），点选任意位置命中节点并联动属性/层级树；此模式下设备控制轨（Home/电源/音量/旋转/冻结/审查/只读）全部锁定，避免与静态视图错位。
- 【重置】= 清空筛选/高亮/选中并**切回实时投屏**；控制轨「抓取布局快照」按钮同样进入布局查看（高亮态）。
- 切换设备或设备离线自动回 `live`。

### 3. 新增【导出】

- ElementTab 工具栏「重置」旁新增【导出】：把当前快照重建为 `<hierarchy>` XML（含全部节点属性，转义安全）；
- 壳新增 `layout:export` IPC：`showSaveDialog` 让用户自选存储路径后写入文件；浏览器（无壳）环境兜底为直接下载；
- 失败/成功均写入 `[LayoutSee][元素查看]` 日志。

### 4. 默认窗口尺寸

`BrowserWindow` 从 1440×900（min 1280×800）调整为 **1000×720（min 940×640）**，对齐用户标注的红框区域；工作台布局在 940px 宽度下已验证可容纳（控制轨 68 + 设备区 ≥330 + 任务面板 ≥520）。

### 5. scrcpy 体验（延迟 / 花屏 / 热区 / 黑边）

| 问题 | 根因 | 修复 |
|---|---|---|
| 热区点击错乱 | 点击坐标按**推流分辨率**（472×1024，max_size 缩放）换算，而设备期望物理像素（1080×2340）——所有 tap 都落在左上角约 1/5 区域 | 新增 `GET /devices/{id}/window-size` 端点；DeviceCanvas 按**设备物理分辨率**换算坐标 |
| 画面污染 | 丢帧（解码积压）后继续解码后续 delta 帧，参考帧缺失产生花屏，且长 GOP 导致迟迟不恢复 | 编码端加 `video_codec_options=i-frame-interval=2`（短 GOP）；解码端丢帧后进入「等关键帧」状态，收到 IDR 才恢复；解码器出错自动重建 |
| 延迟 | 订阅队列过深（90 帧 ≈ 3s 积压上限） | 队列深度 90→30，drop-oldest 保实时；快照查看模式挂起推流，省 CPU |
| 黑边/外壳 | `.device-frame` 5px 黑边 + 黑底 + 32px 留白 | 对齐 scrcpy 原生观感：去粗边框、1px 细边、留白 32→14px、圆角 14px |

### 三轮验证

- `window-size` 真机返回 1080×2340；带 i-frame-interval 的流正常出帧（滑动场景 5s 92 帧）；
- Web 构建通过、解码器单测 4 项、Core 34 项、契约 5 项、壳 8 项全绿；
- 导出 IPC 与 preload 白名单已接通（`layout:export`）。

---

## ⚠️ 二轮修正（2026-08-29 晨）：「立即抓取」501 的真正根因

第一轮把 501 归因于 OPTIONS 预检（修复方向正确但不是主因）。用户复测抓取仍 501 后，借助新增的 UI 日志定位到**完整证据链**：

```
[工作台] 抓取 UI 快照 完成 3194ms          ← POST 抓取成功！
[工作台] 抓取失败 HTTP_501 请求失败（501）   ← 失败的是下一步 GET 快照详情
```

用 curl 在同一条 keep-alive 连接上复现，抓到决定性报文：

```
< HTTP/1.1 501 Unsupported method ('{}POST')
```

### 真正根因（两个叠加）

1. **请求体残留污染 keep-alive 连接**：`POST /devices/{id}/snapshots` 的处理分支**从不读取请求体**，Web 发送的 2 字节 `{}`（Content-Length: 2）在响应后残留在 socket 缓冲区；同连接上的下一个请求（GET 快照详情）被解析成 `{}GET /...` → Python http.server 报 `501 Unsupported method ('{}GET')` HTML 错误页 → 前端显示「请求失败（501）」。此前每个 curl 测试都是独立连接，所以单请求测试永远无法复现。
2. **`GET /api/v1/snapshots/{snapshotId}` 路由根本不存在**：只实现了二级子路径（`/xpath`、`/screenshot` 等），抓取成功后 Web 读取快照详情必然 503「未实现的接口」——被问题 1 的 501 一直掩盖。

### 二轮修复

| 修复 | 文件 | 说明 |
|---|---|---|
| 请求体统一排空 | `core/server.py` | `_handle` 入口先 `_drain_request_body()` 并缓存，`_read_body` 读缓存；任何带 body 的请求（含走不到 `_read_body` 的分支）都不会再残留字节 |
| 框架错误强制断连 | `core/server.py` | `send_error` 覆写置 `close_connection=True`，未知方法 501 等框架错误后不再复用连接 |
| 快照详情路由 | `core/server.py` | 新增 `GET /api/v1/snapshots/{snapshotId}` 返回完整快照（节点/前台应用/截图元数据）；过期返回 `SNAPSHOT_STALE` |
| 媒体流连接不复用 | `core/server.py` | `media/stream` 置 `close_connection`，推流结束即断开 |
| Core 请求级日志 | `core/server.py` | 每个请求向 stderr 输出 `[request] METHOD path -> status 耗时ms 错误码`，由壳收集到 `logs/<date>-core.log` |
| Web 网络层日志 | `web/api/client.js` | 所有非 2xx 记录 `method path → HTTP status`（error 级）、写请求与慢请求（>5s）记录 info 级；`/api/v1/ui-logs` 自身豁免防递归 |
| 失败步骤点名 | `web/.../WorkbenchPage.jsx` | 抓取与「读取快照详情」分开计时埋点，失败日志直接指名哪一步 |
| 日志解耦 | `web/api/logger.js` + `web/app/LoggingBridge.js` | 上报通道改为注入式（`configureUiLogUploader`），消除 client↔logger 循环依赖 |

### 二轮验证

- curl 单连接复现序列：`GET devices → POST capture → GET snapshots/{id}` 全部 200（修复前：503/501/503）；
- 回归测试 `test_keepalive_body_leftover_does_not_poison_next_request`：同连接「PUT settings(403，不读 body) → GET info(200)」，修复前该用例必现 501；
- 真机抓取 → 快照详情 200（65 节点 + 前台应用 + 截图元数据）；
- Core 34 项 / Web 4 项 / 契约 5 项 / 壳 8 项单测全绿。

---

## Bug 1（①号）：投屏画面黑屏 / 只有「截图模式」，要求接入 scrcpy 实时投屏

### 现象

工作台左侧设备画面区域一直黑屏（或上次最后一帧），角标固定显示「截图模式」，800ms 截图轮询既慢又费力。

### 根因

V0.1 按规格偏差记录以「截图轮询降级模式」先行，scrcpy 实时媒体链路本来就被推迟到后续 Story（见 `summary.md` 验证结果第 7 条）。黑屏本身是叠加问题：设备熄屏/离线时 screencap 返回纯黑或失败，UI 没有把「设备无画面」与「模式」区分开。

### 修复（本次直接落地 scrcpy 实时链路）

按 `technical-design.md` §8.3 的上游复用规则实现（scrcpy 为 Apache-2.0，server jar 记录版本/哈希/许可证）：

- **Core 侧**（新增 `repos/core/src/layoutsee_core/media.py`）：
  - `ScrcpySession`：推送 `scrcpy-server-v2.7.jar`（资源随包，`resources/scrcpy-server-v2.7.jar`）→ 通过 ADB wire 协议 `shell:` 服务拉起 `app_process com.genymobile.scrcpy.Server`（`tunnel_forward=true, send_frame_meta=true, control=false, audio=false, max_size=1024`）→ `localabstract:scrcpy` 隧道读取 H.264 Annex-B 帧记录（`[pts u64][len u32][payload]`，pts bit63=config、bit62=key）。
  - `MediaHub`：每设备懒启动单会话、多订阅者扇出、无观众 3 秒自动回收（`reap_idle` 后台线程）、失败可重试。
  - 新端点 `GET /api/v1/devices/{id}/media/stream`：chunked 流转发（头 `LSS1`+宽/高/fps，每帧原样转发 scrcpy 记录，`len=0` 为心跳）。
  - 新端点 `GET /api/v1/devices/{id}/media/capabilities` 返回 `{mode:"scrcpy", live:true}`。
  - 会话串行规则不变：tap/swipe 等写操作仍走统一 HTTP 动作队列（不启用 scrcpy control 通道）。
- **Web 侧**（新增 `repos/web/src/media/scrcpyStream.js`，改造 `DeviceCanvas.jsx`）：
  - `ScrcpyViewer`：fetch 流式读取 → 帧记录解析 → SPS/PPS 构建 **avcC description** → `VideoDecoder`（WebCodecs）解码 → canvas 渲染；积压丢帧保实时；静止画面长超时不误杀。
  - DeviceCanvas 按能力协商：scrcpy 可用显示「实时投屏」，连续 3 次失败自动降级回截图轮询；坐标映射、审查模式、冻结、只读交互全部不变。

### 调试中踩过的坑（重要）

1. **avcC description 长度必须精确**：初版多写了 5 个尾部字节，Chromium `VideoDecoder` 显示 `configured`、`decode()` 全部成功、却**一帧都不输出**（无任何报错）。改为 `8 + sps.length + 3 + pps.length` 后 41/41 帧解码。离线变体实验确认：`annexb` 内联参数集（不带 description）在 Chromium 上不可用。
2. **`_watch_shell` 静默误判**：`log_level=error` 时 scrcpy server 正常路径零输出，shell 读取 1 秒超时曾被当成「会话结束」→ `reap_idle` 把健康会话回收。已改为超时继续等待，仅 EOF 才判退出。
3. **静止画面读取超时**：视频读取超时从 1s 放宽到 15s（静止画面可能长时间无新帧；`close()` 会先关 socket 打断阻塞，不影响退出速度）。

### 验证

- 真机（SM_S9310 / Android 16）实测：472x1024@24fps 实时流，1 配置帧 + 1 IDR + 连续增量帧。
- headless Chrome 端到端：8 秒解码 64 帧，canvas 渲染 3600/3600 采样像素非零。
- 打包制品内复测：PyInstaller onedir 资源路径正确，打包 Core 拉流 26 帧。
- 回归：Core 32 项单测、Web 4 项解码器单测（含 avcC 精确长度断言）、契约 5 项、壳 8 项全绿。

---

## Bug 2（②号）：点「立即抓取」提示「请求失败（501）」

> 第一轮分析（保留存档，主因见文首「二轮修正」）：Core 基于 Python `http.server` 只实现 GET/POST/PUT，OPTIONS 预检返回 501 HTML，前端展示兜底文案「请求失败（501）」。已修复 `do_OPTIONS` → 204；同轮还发现并修复了带斜杠子路径的死路由。真正的抓取链路主因是 keep-alive 请求体残留 + 快照详情路由缺失，见文首。

---

## Bug 3：点设置开关总提示「不允许修改的设置：schemaVersion」

### 根因

两端叠加：

1. `SettingsPage.save()` 把**整个设置对象**（含 `schemaVersion`）随补丁回传：`api.saveSettings({ ...settings, ...patch })`；
2. `SettingsStore.update()` 对任何不在 `UPDATABLE_KEYS` 的键直接抛 `INVALID_ARGUMENT`。

`schemaVersion` 是文件格式版本（Core 持久化时自动维护），不是用户可改项，被回传后必然报错。

### 修复

- 前端 `SettingsPage.jsx`：只提交变更字段 `api.saveSettings(patch)`；
- 后端 `settings.py`：新增 `SYSTEM_KEYS = {"schemaVersion"}`，补丁中出现的系统字段**静默忽略**（防其它客户端同类问题），未知键仍然报错；持久化始终重写 `schemaVersion`。

### 验证

- `PUT /api/v1/settings` 带 `{"schemaVersion":"1.0","theme":"dark"}` → 200，落盘内容 `schemaVersion` 恒为 `1.0`；
- 单测 `test_schema_version_patch_is_ignored` 回归覆盖。

---

## 增强：四个 Tab 统一 Tag 日志（可贴给排查用）

### 实现

- 新增 `repos/web/src/api/logger.js`：统一 Tag `[LayoutSee][Tab名]`，console 输出 + 内存缓冲 1.5s 批量上报；
- Core 新端点 `POST /api/v1/ui-logs`（需会话令牌）：追加写 `~/Library/Application Support/LayoutSee/logs/ui-YYYY-MM-DD.log`，保留 7 天（`uilogs.py`），制表符分隔单行：`时间\t级别\tTag\t消息`；
- 埋点范围：
  - **工作台**（WorkbenchPage）：抓取快照（含耗时/节点数/警告）、抓取被忽略、只读开关；
  - **常用**（CommonTab）：读前台应用、启停应用、应用列表查询及失败；
  - **元素查看**（ElementTab）：快照加载、XPath 查询（含命中数/零命中）、选择器生成；
  - **MCP**（McpTab）：工具列表加载/失败、配置复制；
  - **布局智能**（IntelligenceTab）：摘要生成（tokens/partial）、诊断生成（发现数）；
  - **投屏**（DeviceCanvas）：模式协商、scrcpy 流建立/异常/降级、注入动作。
- 查看方式：设置 → 安全 → 「打开日志目录」，或菜单栏帮助 → 打开日志目录，`ui-*.log` 即前端日志（与壳日志 `layoutsee-*.log` 并列）。

---

## 改动文件清单

| 工程 | 文件 | 变更 |
|---|---|---|
| core | `src/layoutsee_core/media.py` | 新增：ScrcpySession / MediaHub / ADB wire 隧道 |
| core | `src/layoutsee_core/uilogs.py` | 新增：前端日志落盘 |
| core | `src/layoutsee_core/server.py` | OPTIONS 204、三级子路由、媒体流端点、ui-logs 端点、chunked 助手 |
| core | `src/layoutsee_core/settings.py` | SYSTEM_KEYS 静默忽略 |
| core | `src/layoutsee_core/bootstrap.py` | 装配 MediaHub / UiLogStore / 回收线程 |
| core | `src/layoutsee_core/__main__.py` | 退出时停止媒体会话 |
| core | `src/layoutsee_core/resources/scrcpy-server-v2.7.jar` | 新增（Apache-2.0，取自 source/uiautodev 同源发行物） |
| core | `tests/test_routing_fixes.py`、`tests/test_diagnostics_settings.py` | 新增/扩展回归 |
| core | `scripts/diagnose_scrcpy.py`、`scripts/repro_session.py` | 新增：真机 scrcpy 排查工具 |
| web | `src/media/scrcpyStream.js` | 新增：流解析 + WebCodecs 解码渲染 |
| web | `src/api/logger.js` | 新增：统一 Tag 日志 |
| web | `src/api/client.js` | + uiLogs API |
| web | `src/features/workbench/DeviceCanvas.jsx` | scrcpy/截图双模式与降级 |
| web | `src/features/workbench/WorkbenchPage.jsx` | 抓取/只读日志 |
| web | `src/features/workbench/tabs/{Element,Common,Mcp,Intelligence}Tab.jsx` | 各 Tab 日志埋点 |
| web | `src/features/settings/SettingsPage.jsx` | 补丁式保存 + 投屏文案更新 |
| web | `src/styles/app.css` | canvas.device-pixel 样式 |
| web | `tests/scrcpy-stream.test.mjs` | 新增：解码器纯函数单测 |
| mac | `scripts/package.mjs` | PyInstaller 打入 scrcpy jar；manifest 记录 scrcpy 版本/哈希/许可证 |

## 遗留与后续

- 投屏写操作仍走 `adb shell input`（与截图模式一致）；scrcpy control 注入通道（更低延迟触控）留给后续 Story。
- 群控预览页（GroupPreviewPage）暂仍为截图模式，可按同一套 `media/stream` 端点接入。
- 用户验收路径：退出旧 LayoutSee → 安装 `repos/mac/release/LayoutSee-0.1.0-arm64.dmg` → 连接设备确认①实时投屏、②立即抓取、③设置开关；如仍有问题，到日志目录复制 `ui-*.log` 与 `layoutsee-*.log` 反馈。
