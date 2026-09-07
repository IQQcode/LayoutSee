# ZCode macOS 端技术栈调研

> 调研日期：2026-08-27 ｜ 调研对象：本机安装的 ZCode 3.9.2（`/Applications/ZCode.app`，bundle id `dev.zcode.app`）
> 调研方法：App Bundle 拆包（Info.plist / Frameworks / app.asar 索引与内容抽样）+ 公开资料交叉验证
> 用途：为 LayoutSee macOS 端技术选型与「macOS 原生过渡动效」设计提供对齐基准
> 关联：[ZCode 客户端设计规范（视觉基准）](../../research/design/zcode-client-design-spec.md)（基于 3.9.1，本文为 3.9.2 增量）

## 1. 结论速览

ZCode macOS 端是 **Electron 桌面应用**，主进程与渲染进程均为 JavaScript/TypeScript 工程。一句话概括：**Electron（Chromium + Node）+ Vite/React 19 渲染层 + Tailwind v4 token 体系 + 自研 `@zcode/*` monorepo + 原生 NAPI 模块（终端 / macOS 可访问性）**。

| 层 | 技术 | 版本证据 |
|---|---|---|
| 桌面壳 | Electron | 41.0.3（Frameworks 内 `Electron Framework.framework`） |
| 壳更新 | Squirrel.Mac + electron-updater | `Squirrel.framework`、`electron-updater@6.8.3`、`app-update.yml`（generic provider） |
| UI 框架 | React | 19.2.4（package.json dependencies 实锤） |
| 前端构建 | Vite（renderer）+ esbuild 系（main/preload/host） | `out/renderer/index.html` 的 `modulepreload` 与 2751 个按需 chunk；`out/main/*.js` chunk 引用风格 |
| 样式 | Tailwind CSS（v4 token 体系） | `styles-*.css` 含 `--tw-` CSS 变量 |
| 动效 | framer-motion / motion 12.38.0 + 内联 CSS keyframes | node_modules 实锤 + `index.html` 启动动画源码 |
| 组件体系 | Radix UI（shadcn 风格）+ cva + cmdk | `@radix-ui/*`、`class-variance-authority`、`cmdk` |
| 图标 | lucide-react | renderer 按图标拆出数千个 chunk |
| 状态管理 | Redux Toolkit + Zustand + XState + TanStack Query | `@reduxjs`、`xstate`、`@tanstack`（spec 已确认 Zustand） |
| 编辑器/终端 | Monaco（spec 确认）、node-pty（本地）+ ssh2（远程）、@xterm | `node-pty@1.0.0`（unpacked 原生模块）、`ssh2@1.16.0`、`@xterm` |
| 浏览器自动化 | playwright-core 1.59.1 | package.json 实锤 |
| 图像处理 | sharp 0.34.5 | package.json 实锤 |
| 辅助进程（CUA） | 独立 `.app` + 原生 NAPI（macOS Accessibility） | `cua-helper/ZCode Computer Use.app` 内含 `ax_native.node` |
| MCP | @modelcontextprotocol SDK | `@modelcontextprotocol/*` |
| AI 侧 | Vercel AI SDK 网关（@ai-sdk/*）+ 模型目录 | `@ai-sdk/gateway`、`model-providers/*.json`（智谱 GLM 模型清单） |
| 可观测性 | OpenTelemetry + 阿里 ARMS | `@opentelemetry/*`、`@arms/rum-electron` |
| 打包 | electron-builder 体系（asar） | `app.asar`（297MB）、`app.asar.unpacked` |
| 内置工具链 | ripgrep / ugrep / bfs 二进制随包分发 | `Resources/tools/` |
| 进程结构 | main / renderer / preload / host / scheduler 五产物 | `out/.main-build-ready` 等标记文件 |
| 数据与配置 | `~/.zcode/` 目录（config、db、log、plugins） | 本机 `~/.zcode/cli/` |

## 2. 证据来源

### 2.1 拆包证据（3.9.2，2026-08-27 实测）

| 证据 | 位置 | 说明 |
|---|---|---|
| Electron 版本 | `Contents/Frameworks/Electron Framework.framework` | `CFBundleVersion = 41.0.3` |
| Squirrel 更新框架 | `Contents/Frameworks/Squirrel.framework` + `Mantle.framework` + `ReactiveObjC.framework` | macOS 增量更新标准组合 |
| 更新配置 | `Contents/Resources/app-update.yml` | `provider: generic`，`url: http://localhost:8081`（内网分发，团队版形态） |
| 主包 | `Contents/Resources/app.asar`（297MB） | 含 `node_modules` + `out/` 产物 + `package.json` |
| 原生模块 | `app.asar.unpacked/node_modules/` | `node-pty`、`ssh2`（需原样落盘，不进 asar） |
| CUA 辅助 App | `Resources/cua-helper/ZCode Computer Use.app` | bundle id `dev.zcode.cua-helper`，内含 `ax_native.node`（macOS Accessibility 原生插件）与 `sharp` 依赖 |
| 模型目录 | `Resources/model-providers/` | `models_catalog_china_llm_zcode_*.json`（智谱 GLM 系模型清单，随客户端下发） |
| 内置二进制 | `Resources/tools/` | `ripgrep`、`ugrep`、`bfs` |

### 2.2 包信息（package.json，app.asar 内）

- 包名 `@zcode/desktop`，`type: module`，`main: out/main/index.js`，`homepage: https://zcode.z.ai`，作者 `dev@zcode.z.ai`（智谱）。
- Monorepo workspace 依赖：`@zcode/client`、`@zcode/server`、`@zcode/rpc`、`@zcode/services`、`@zcode/shared`、`@zcode/ui`、`@zcode/zcode-cua`。
- 关键运行时依赖：`react@19.2.4`、`react-dom@19.2.4`、`electron-updater@6.8.3`、`node-pty`、`playwright-core@1.59.1`、`sharp@0.34.5`、`ssh2`、`ws`、`undici`、`yaml`、`@lydell/node-pty-*`（平台专用包）。

### 2.3 动效实现证据（本调研的核心增量）

`out/renderer/index.html` 内联的启动动效源码，是 ZCode 官方「macOS 原生质感动效」的直接样本：

```css
/* 首屏容器：就绪前透明，就绪后 0.16s 淡入 */
#root { opacity: 0; transition: opacity 0.16s ease; }
body.zcode-startup-ready #root { opacity: 1; }

/* 启动 Logo：0.72s 弹簧曲线（easeOutQuint 近似，带 overshoot） */
@keyframes startup-logo-pop {
  0%   { opacity: 0; transform: scale(0.72); }
  38%  { opacity: 1; transform: scale(1.045); }
  58%  { transform: scale(0.985); }
  76%  { transform: scale(1.008); }
  100% { opacity: 1; transform: scale(1); }
}
.startup-logo-shell {
  animation: startup-logo-pop 0.72s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

/* 减弱动态效果：立即到位，不做动画 */
@media (prefers-reduced-motion: reduce) {
  .startup-logo-shell { opacity: 1; transform: scale(1); animation: none; }
}
```

要点：

1. **曲线选择**：`cubic-bezier(0.22, 1, 0.36, 1)` 是 macOS 生态最常见的「快速进、软着陆」曲线（easeOutQuint 近似），配合关键帧 overshoot（1.045 → 0.985 → 1.008 → 1）模拟原生弹簧回弹。
2. **双阶段启动**：`opacity 0.16s` 的容器淡入与 `0.72s` 的 Logo pop 分离——短的先完成（窗口可交互感），长的负责「仪式感」，且互不阻塞。
3. **就绪钩子**：`body.zcode-startup-ready` 由主进程/渲染进程在首帧渲染完成后添加，而非任意定时器。
4. **无障碍**：`prefers-reduced-motion: reduce` 下动画完全关闭，直接呈现终态。
5. **工具克制**：视觉基准调研（3.9.1）确认日常交互动效只有 `transition-colors`（悬停 150ms 级）、`transition-transform`（箭头旋转）、`animate-spin`（加载）三类；`framer-motion@12.38.0` / `motion@12.38.0` 在依赖中但未在 renderer bundle 中大面积出现，用于少数需要 spring/AnimatePresence 的场景。

### 2.4 公开资料交叉验证

- [zcode-linux（第三方 Linux 移植）](https://github.com/robustonian/zcode-linux)：确认 ZCode Desktop 是 Electron 应用，UI/逻辑在平台无关的 `app.asar` 中，含 node-pty 原生模块。
- Dmitriy Kovalenko 的二进制拆解（媒体报道）：Node.js + React + Redux + XState + Electron，804 个依赖，使用 Vercel AI SDK 连接模型，内置 ripgrep 做文件搜索，支持 `ZCODE_HTTP_PROXY` 等代理环境变量。
- 官方文档 [zcode.z.ai](https://zcode.z.ai)：Z.ai（智谱）出品的 Agent 优先编程环境，GLM Coding Plan 订阅或 BYOK；数据与配置在 `~/.zcode/`。

## 3. 分层详情

### 3.1 壳层（Electron main）

- 单窗口 / 多辅助窗口模式：主窗口 + CUA 权限面板（独立窗口，`out/preload/cuaPermissionPanel.cjs`）+ 嵌入式浏览器（`embeddedBrowserJavaScriptDialog.cjs`）+ 编码计划 WebView（`codingPlanWebview.cjs`）+ 进程监视（`processMonitor.cjs`）。
- preload 按窗口类型拆分多份 cjs（`index.cjs` / `browserVideoRecorder.cjs` / `processMonitor.cjs` …），只向指定窗口注入对应能力——**按窗口最小暴露**的安全模型。
- 主进程经 `@zcode/rpc` 与渲染进程通信（monorepo 内自研 RPC 层）。
- `out/scheduler/` 为独立调度进程（定时任务），`out/host/` 为 host 侧能力（SSH / 浏览器自动化等）。

### 3.2 渲染层（React 19 + Vite）

- Vite 产物：`out/renderer/`（index.html + assets 2751 个 chunk，lucide 图标按需拆包，`modulepreload` 预载 react/jsx-runtime 等公共 chunk）。
- 样式：Tailwind（`--tw-` 变量），对齐视觉基准文档 3.x 的 token 体系；`styles-*.css` 达 4.3MB（含全部主题与组件样式）。
- 编辑器：Monaco（spec 确认）；文档预览：pdfjs-dist、docx/xlsx/pptx 预览引擎（WASM，见 `duke_sheets_wasm_bg.wasm`）；公式 KaTeX；代码高亮 highlight.js + Shiki（`@shikijs`）；图表 chart.js/echarts/d3；流程图 @xyflow；拖拽 @dnd-kit；轮播 embla。
- 国际化：react-intl（en-US / zh-CN，spec 确认）。

### 3.3 辅助进程

- **CUA（Computer Use）**：独立 `ZCode Computer Use.app`（`dev.zcode.cua-helper`），用原生 NAPI `ax_native.node` 走 macOS Accessibility（AX）总线——即「原生屏幕控制」能力是**独立进程 + 原生模块**实现，不依赖渲染层。
- **host / scheduler**：独立 bundle，承载 SSH 远程开发与定时调度。

### 3.4 分发与更新

- electron-builder 打包（dmg + asar），Squirrel.Mac 做增量更新，`app-update.yml` 指向 generic 服务器。本机版本为内网分发（`localhost:8081`），说明更新地址可配置、可私有化部署——与 LayoutSee「不依赖线上站点」的诉求同构。

### 3.5 可观测性与监控

- `@opentelemetry/*`（trace/metrics）+ `@arms/rum-electron`（阿里云 ARMS 前端监控，Electron 专版）。
- 日志目录 `~/.zcode/log/`（本机存在），与 LayoutSee 规划的 `~/.layoutsee/logs/` 约定一致。

## 4. 对 LayoutSee macOS 端的启示

1. **壳选型维持 Electron 是低风险路径**：PRD 4.9 与 `repos/mac` README 已定 Electron；ZCode 以同栈跑通了 macOS 桌面 Agent 产品全流程（签名公证、Squirrel 更新、原生模块、多进程），路径已被验证。LayoutSee 起步可用当前 stable（调研时 ZCode 用 41.0.3），不必追同代小版本。
2. **动效基调对齐**：ZCode 的「macOS 原生感」= 系统字体 + 短时长 + 弹簧曲线 + overshoot 细节 + reduced-motion 全量降级，而非大面积玻璃/渐变。这与 DESIGN.md 第 2.6 节「原生感来自细节」完全一致，LayoutSee 的页面切换与按钮动效应沿用同一条曲线 `cubic-bezier(0.22,1,0.36,1)` 与 100–300ms 时长区间。
3. **动效库策略**：日常悬停/按压用 CSS transition（成本最低）；页面切换、Tab 指示线等需要「退出动画 + 共享元素」的场景用 motion（framer-motion 12）的 `AnimatePresence` / `layoutId`。不必为所有动效都引入 JS 动画库。
4. **进程拆分借鉴**：LayoutSee 的「内核守护」对应 ZCode 的 host/scheduler 拆分思路——壳主进程只管窗口与 sidecar 生命周期，能力下沉到独立进程，preload 按窗口最小暴露。
5. **分发借鉴**：`app-update.yml` generic provider + 可配置地址的模式可直接套用，满足「内部定制分发、不依赖线上站点」。
6. **不建议照搬**：ZCode 包体 297MB（Monaco、playwright、echarts、pptx 预览等重型依赖堆叠）；LayoutSee V0.1 无编辑器/文档预览需求，应保持依赖精简，预估包体可控制在 100–150MB 级。

## 5. 增量结论（相对 zcode-client-design-spec.md）

| 维度 | spec（3.9.1） | 本次调研（3.9.2） |
|---|---|---|
| Electron 版本 | 未注明 | 41.0.3 |
| React | 18 | 19.2.4 |
| 动效 | 「无弹跳、无位移动画，克制为主」 | 补充：启动动效用 spring 曲线 + overshoot；framer-motion/motion 12.38.0 在依赖中；页面级动效存在实现样本 |
| 更新机制 | `app-update.yml` | 补充：Squirrel.Mac + electron-updater 6.8.3 + generic provider 可配置地址 |
| 原生模块 | node-pty + ssh2 | 补充：CUA 用独立 App + `ax_native.node`（AX 总线原生 NAPI） |
| 监控 | 未提及 | `@opentelemetry` + `@arms/rum-electron` |
| MCP | 功能层面 | 补充：客户端内置 `@modelcontextprotocol` SDK |
