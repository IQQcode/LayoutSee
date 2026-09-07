# CLAUDE.md

本文件与 `AGENTS.md` 互为入口，内容一致。以 `AGENTS.md` 为单一维护源，此处仅做索引转发，避免双份维护漂移。

## Agent 工作规则摘要

- **工作入口**：先读 `docs/index.md` 定位业务上下文，改代码前读根目录 `INDEX.md`（代码模块索引），再读 `source/index.md` 与 `source/<repo>/` 三件套了解仓库，最后动手。
- **目录速览**：`docs/` 知识、`INDEX.md` 代码索引、`specs/` 规格沉淀、`skills/` 业务 Skill、`hooks/` 护栏、`agents/` 自定义 Subagent、`repos/` 本工程源代码（contracts / core / web / mac / plugins）、`source/` 说明索引与外部参考工程。
- **工作流程**：澄清需求 → 拆卡 → 用 Subagent 隔离上下文实现 → 非可视化验证先行，人做最终可视化确认 → 沉淀知识。
- **Subagent 规范**：探索用 Explore，跨模块执行用 General，验证用编程式断言；不重复造默认 Subagent。
- **编写规则**：只沉淀「非显而易见」的知识；可执行流程进 Skill，product / design / env 信息进 Docs。

> 完整规则见 [AGENTS.md](./AGENTS.md)，本文不重复展开。
