---
name: Story
description: >
  LayoutSee 需求实现拆解：Story 落盘目录的入口与拆解约定
---

# STORY.md 需求实现拆解说明

LayoutSee 需求实现拆解的入口文档。每个大 Feature 的开发拆解（Story / Task）沉淀在 `docs/story/`，本文提供拆解约定与路由。

## 拆解约定

- 复杂需求拆成可独立验证的 Story / Task，每个 Story 可绑定 iCafe 卡片。
- Story 落盘命名：`yy-mm-dd-功能名称.md`（参考贴吧 plans 命名规范）。
- 拆解内容至少包含：目标、范围、验收标准、涉及仓库、依赖关系。
- 拆解是 Agent 执行过程的产物，且对后续任务有参考意义，落盘后由人 review 确认。

## 当前拆解

| 日期 | Story | 状态 |
|------|-------|------|
| 26-08-27 | [ZCode macOS 技术栈调研](./story/26-08-27-zcode-macos-技术栈调研.md) | 已完成，待 review |
| 26-08-27 | [技术评审：V0.1 macOS 端（桌面壳 + 统一 Web UI + 原生过渡动效）](./story/26-08-27-技术评审-macos桌面壳与原生动效.md) | 待评审 |
| 26-08-28 | [Story-0827 M0：契约与工程初始化](./story/26-08-28-story-0827-m0-契约与工程初始化.md) | 已完成，待 review |
| 26-08-28 | [Story-0827 macOS arm64 本地候选包](./story/26-08-28-story-0827-macos-arm64本地候选包.md) | 已构建，待人工功能测试 |
| 26-08-31 | [Story-0831 Web 通用端：浏览器成为一等宿主](./story/26-08-31-story-0831-web通用端.md) | 编码与非可视化验证完成，待真机 review |
| 26-09-07 | [macOS 双架构（arm64 + x64）候选包](./story/26-09-07-macos-双架构候选包.md) | x64 产物构建完成，待 2020/Intel 机器实测 |

## 路由

- 需求源头：`./feature/UI-LayoutSee需求文档PRD.md`
- 拆解落盘目录：`./story/`
- Agent 工作规则：`../AGENTS.md`
