# AGENTS.md

本文描述 Agent 在 LayoutSee Workspace 中的工作规则。**不讲业务逻辑，不介绍仓库是做什么的**，业务上下文请走 `docs/index.md` 知识入口。

## 1. 工作入口

接需求后，先建立上下文，再动手：

1. 读 `docs/index.md`，定位本次需求涉及的产品、设计、调研文档。
2. 要改代码时，先读根目录 `INDEX.md`（代码模块索引：各文件职责、跨工程速查、已知坑）。
3. 涉及具体仓库时，读 `source/index.md` 定位工程，再读对应 `source/<repo>/overview.md` 了解仓库定位，`setup.md` 了解构建与启动，`test.md` 了解测试方式。
4. 涉及 Android 布局感知时，加载 `skills/layout-inspector`。
5. 不确定 Agent 在该仓库的行为约束时，读对应仓库内的 `AGENTS.md`（如 `source/layoutsee-prototype/AGENTS.md`）。

## 2. 目录速览

```text
docs/      人维护的知识（产品/设计/调研/环境/需求拆解），Agent 无法从代码读出的上下文
INDEX.md   代码模块索引：改代码前的第一站
specs/     技术规格沉淀：一个 Story 一个目录（doc.md 设计 + summary.md 实施总结）
skills/    业务 Skill，可被当前 workspace 识别
hooks/     Hook 注册表，Agent 行为的硬性护栏
agents/    自定义 Subagent 定义
repos/     本工程源代码：contracts 契约 / core Python 内核 / web 前端 / mac 桌面壳 / plugins 随包插件
source/    说明索引（index.md 与各工程 overview / setup / test 三件套）与外部参考工程代码
```

## 3. 工作流程

- 需求进来：先澄清目标、范围与验收标准，识别「未知的未知」，再进入拆卡与实现。
- 拆卡：复杂需求拆成可独立验证的 Story / Task，一次会话装不下时善用 handoff 交接。
- 实现：鼓励用 Subagent 隔离上下文；修改代码前先读对应 `source/<repo>/setup.md` 与仓库内 `AGENTS.md`。
- 验证：不只做可视化验证，先完成非可视化验证（构建、单测、静态检查），人负责最终可视化确认。
- 收尾：产出沉淀到 `docs/story/`，运行过程中发现的新知识写入对应 docs 或 skill。

## 4. Subagent 使用规范

- 探索陌生代码库：用 Explore 类 Subagent（fast / medium / thorough），不要在主会话里大量盲搜。
- 跨模块排查：用 General 类 Subagent 执行多步任务，主 Agent 只做编排与裁决。
- 验证类工作：用验证类 Subagent 做编程式断言，不要相信「看起来完成了」。
- 只有需要长期复用的自定义角色，才在 `agents/` 定义；默认 Subagent 已覆盖大部分场景，避免过度沉淀。

## 5. 编写规则

- 文档：只整理「非显而易见」的内容（部署信息、设计原则、常见错误、分支命名规则等）；能从代码读出的 API 文档、编码规范不重复整理。
- 代码：遵循目标仓库既有风格；改动前先看仓库内 AGENTS.md 是否有额外约束。
- Commit：描述部分用中文，保留 `feat:` / `fix:` 等英文标签与卡片号。
- Docs 与 Skills 的分工：可执行的流程优先沉淀为 Skill；Docs 集中整理 product、design、env 等信息，其余交给 Agent 自我产生和销毁。
