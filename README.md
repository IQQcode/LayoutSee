# LayoutSee

> 面向 Agent 的移动端运行时视图感知入口：连接 Android / iOS / HarmonyOS 真机，提供实时投屏与操控、结构化 UI 层级抓取、语义摘要、布局异常诊断和 MCP 服务，把移动设备运行时视图转换为 Agent 可读、可定位、可操作的结构化资源。

LayoutSee 以 Workspace 形态组织：本仓库既是「指挥仓」（文档、Skill、Hook、索引），也直接承载五个工程模块的源代码，方便任何角色（PM / RD / FE / QA）+ Agent 完成从需求到验证的端到端开发。

代码层面的模块索引在 [INDEX.md](./INDEX.md)（各文件职责与关键点），仓库层面的构建/测试说明在 [source/index.md](./source/index.md)。

## 仓库结构（完整文件树）

```text
LayoutSee/                          ← 指挥仓根目录
├── .claude/                        ← Claude Code 生态入口（软链 skills / agents）
│
├── AGENTS.md                       ← Agent 行为规范与工作规则（入口文档）
├── CLAUDE.md                       ← 同上（Claude 入口，与 AGENTS.md 互通）
├── README.md                       ← 本文件：仓库结构说明（含完整文件树）
├── INDEX.md                        ← 代码模块索引：各工程文件职责、关键点与已知坑
├── package.json                    ← npm workspaces 根（contracts / web / mac）与全部工程命令
│
├── repos/                          ← 本工程源代码（五个模块）
│   ├── contracts/                  ← 跨进程协议单一事实源（OpenAPI 3.1 + JSON Schema 2020-12）
│   │   ├── openapi/core-v1.yaml    ← HTTP API 定义
│   │   ├── schemas/                ← common / snapshot / mcp / plugin / websocket / test
│   │   ├── fixtures/               ← valid / invalid 契约样例
│   │   ├── generated/              ← TS 与 Python 生成物（禁止手改，check-generated 是门禁）
│   │   ├── compatibility/          ← 版本兼容矩阵
│   │   └── scripts/ tests/
│   ├── core/                       ← 本地 Core：HTTP 服务 + 设备驱动 + 算法（Python 3.12）
│   │   ├── src/layoutsee_core/     ← server / devices / snapshots / media / logcat / plugins / mcp_catalog …
│   │   ├── packaging/              ← PyInstaller 入口
│   │   ├── tests/                  ← unittest（含 fake_core 假 Core）
│   │   └── pyproject.toml          ← uv / Poetry 工程配置
│   ├── web/                        ← Web 端正式工程（Vite 6 + React 19，纯 JS）
│   │   ├── src/                    ← app / api / features（devices、workbench、plugins、settings）/ styles
│   │   ├── public/                 ← 静态资源，含插件侧 SDK plugin-runtime.js
│   │   └── tests/                  ← node:test 单测
│   ├── mac/                        ← macOS 桌面壳（Electron 44，只做进程守护与安全边界）
│   │   ├── src/                    ← main（含 kernel-supervisor）/ preload / bootstrap / shared
│   │   ├── scripts/                ← build / package（PyInstaller + electron-builder）/ lint
│   │   ├── build/ resources/       ← 图标与运行时资源
│   │   └── release/                ← 本地候选包：DMG 与 mac-arm64 解包 app
│   └── plugins/                    ← 随包插件包（无构建步骤，一目录一插件）
│       ├── snapshot-overview/      ← 内置示例：快照统计 + 声明式组合工具
│       └── android-logcat/         ← Android 日志抓取（仅 app 宿主）
│
├── scripts/                        ← 根级工程脚本
│   ├── dev-web.mjs                 ← 浏览器联调：起 Core 拿 READY 并注入会话令牌
│   └── verify-artifacts.mjs        ← 发版产物门禁
│
├── docs/                           ← 人维护的知识（Agent 读不出的上下文）
│   ├── INDEX.md                    ← 知识入口与路由表（AGENTS.md 里写作 docs/index.md）
│   ├── PRODUCT.md / FEATURE.md     ← 产品与需求入口（锚定 feature/UI-LayoutSee需求文档PRD.md）
│   ├── DESIGN.md                   ← 视觉/UI 规范入口（锚定 designs/DESIGN.md）
│   ├── RESEARCH.md                 ← 调研入口（锚定 research/）
│   ├── STORY.md                    ← 需求实现拆解说明（锚定 story/）
│   ├── env/dev.md                  ← 本地开发环境
│   ├── designs/ feature/ research/ ← 设计系统与截图 / PRD / 竞品与视觉基准
│   └── story/                      ← 已完成 Story 的落盘记录与技术评审
│
├── specs/                          ← 技术规格沉淀（doc.md 设计 / summary.md 实施总结）
│   ├── [Story-0827]-mac-app/       ← 桌面壳：spec、technical-design、bugs、ux-feedback
│   ├── [Story-0831]-web/           ← Web 通用端
│   └── [Story-0831]-plugins/       ← 插件模块接口层与契约草案
│
├── skills/layout-inspector/        ← 业务 Skill：Android 运行时视图感知工作流
├── agents/                         ← 自定义 Subagent 定义
├── hooks/                          ← Hook 注册表与护栏脚本
├── assets/                         ← 静态素材（drawio 源文件、竞品与界面截图）
├── properties/                     ← 工程配置说明
│
└── source/                         ← 说明索引与外部参考工程（代码保持原位）
    ├── index.md                    ← 工程登记表：本工程五个模块 + 参考工程
    ├── contracts|core|web|mac/     ← 本工程说明三件套（overview / setup / test）
    ├── plugins/overview.md         ← 插件模块说明（无独立构建与测试命令）
    ├── layoutsee-prototype/        ← 前端原型工程（Vite + React 19）
    └── uiautodev/                  ← 竞品开源 Python 内核（含独立 .git）
```

## 目录职责说明

| 目录/文件 | 职责 | 维护者 |
|-----------|------|--------|
| `AGENTS.md` / `CLAUDE.md` | Agent 行为规范与工作规则，不写业务逻辑，只描述「Agent 在 Workspace 里如何工作」 | 团队共同维护 |
| `docs/` | 人维护的知识：产品、设计、环境、调研、需求拆解，均为 Agent 无法从代码中直接读出的上下文 | PM / RD / FE / QA |
| `skills/` | 业务 Skill：可执行的 Agent 能力封装，当前含 layout-inspector | 有沉淀诉求的成员 |
| `hooks/` | Hook 注册表：Agent 行为的硬性护栏（如禁止改目录、强制检查、行数限制） | 工程负责人 |
| `agents/` | 自定义 Subagent 定义，跨模块任务时隔离上下文 | 工程负责人 |
| `repos/` | 本工程源代码：contracts（契约事实源）、core（Python 本地 Core）、web（工作台 UI）、mac（Electron 壳）、plugins（随包插件包） | RD |
| `INDEX.md` | 代码模块索引：各文件职责、关键点与已知坑，改代码前先看 | RD |
| `specs/` | 技术规格沉淀：每个 Story 一个目录，`doc.md` 设计 + `summary.md` 实施总结 | 需求负责人 |
| `source/` | 说明索引（`index.md` 与各工程 overview / setup / test 三件套）与外部参考工程代码（layoutsee-prototype、uiautodev） | 各仓库 Owner / RD |
| `assets/` | 静态素材：界面截图、drawio 源文件 | 设计 / 产品 |

## 文档导航（给 Agent）

- 想知道「产品要做什么」：读 `docs/PRODUCT.md` → `docs/feature/UI-LayoutSee需求文档PRD.md`
- 想知道「界面长什么样」：读 `docs/DESIGN.md` → `docs/designs/DESIGN.md`
- 想知道「竞品调研结论」：读 `docs/RESEARCH.md` → `docs/research/uiauto-analysis/`
- 想知道「某个功能的代码在哪」：读 `INDEX.md`（模块索引 + 跨工程速查 + 已知坑）
- 想知道「某个仓库怎么构建、怎么测」：读 `source/index.md` 定位后看 `source/<repo>/setup.md` 与 `test.md`
- 想知道「某次需求当初怎么设计的」：读 `specs/[Story-xxxx]-*/doc.md` 与 `summary.md`
- 想解析 Android 布局快照：用 `skills/layout-inspector`
- 想知道「Agent 在这里怎么工作」：读 `AGENTS.md`

## 快速开始

依赖：Node ≥ 22.12、Python 3.12（用 uv 管理）、macOS（桌面壳与打包只支持 arm64）、adb。

```bash
npm install                  # 安装 workspaces 依赖（contracts / web / mac）

npm run dev:web              # 浏览器里联调：起 Core 拿 READY 并注入令牌，开 http://127.0.0.1:4173
npm run test:unit            # 契约 + mac + web + core 全部单测
npm run lint                 # 三个 npm 工程的静态检查
npm run build:all            # 契约漂移门禁 + web 构建 + mac 主进程构建
npm run package:mac          # 出未签名 DMG 与 release/mac-arm64 解包 app
```

生产形态是 Core 托管 web 产物：`uv run --project repos/core python -m layoutsee_core --nonce <64hex> --static-dir repos/web/dist`，打开 READY 行里的回环 URL 即可。

各模块详细命令见 `source/<repo>/setup.md` 与 `test.md`；参考工程见 `source/layoutsee-prototype/setup.md`、`source/uiautodev/setup.md`。
