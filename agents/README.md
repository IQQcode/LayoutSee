# agents/ 自定义 Subagent 定义

本目录存放 LayoutSee Workspace 的自定义 Subagent 定义。当前为空目录，按需补充。

## 使用原则（摘自 AGENTS.md）

- 探索陌生代码库用默认 Explore 类，跨模块执行用默认 General 类，验证用编程式断言。
- **只有需要长期复用的自定义角色**才在此定义，避免过度沉淀导致知识腐化速度快于 Agent 改进速度。
- 定义文件遵循 Subagent frontmatter 规范（name / description / tools / model 等字段）。

## 建议沉淀的自定义 Agent（按需）

| 候选角色 | 适用场景 |
|---------|---------|
| layout-qa | 基于 LayoutSee 快照与 design 规范做还原度检查，产出结构化走查报告 |
| prototype-builder | 按设计规范批量生成前端原型页面，复用 `skills/layout-see` 的能力 |
| cross-repo-debugger | 跨 layoutsee-prototype / uiautodev 排查链路问题时隔离上下文 |

> 每个自定义 Agent 建一个子目录，例如 `agents/layout-qa/agent.md`。定义完成后通过 `.claude/agents` 软链即可被 Claude Code 生态识别。
