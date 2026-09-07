# docs 知识索引

LayoutSee Workspace 的知识入口。Agent 接需求后从这里路由到对应文档；人类成员沉淀知识时也按此结构落位。

## 文档地图

| 类别 | 入口 | 详细文档 | 维护者 |
|------|------|---------|--------|
| 产品设计上下文 | [PRODUCT.md](./PRODUCT.md) | [PRD v0.9](./feature/UI-LayoutSee需求文档PRD.md) | PM |
| 视觉/UI 设计规范 | [DESIGN.md](./DESIGN.md) | [设计系统](./designs/DESIGN.md)、[交互原型](./designs/interaction-prototype.md)、[Stitch 输入](./designs/stich-design.md)、[新版截图](./designs/redesign/) | 设计 |
| 需求说明 | [FEATURE.md](./FEATURE.md) | 同上（PRD 为单一事实源） | PM |
| 调研内容 | [RESEARCH.md](./RESEARCH.md) | [竞品架构调研](./research/uiauto-analysis/uiautodev-analysis.md)、[竞品功能清单](./research/uiauto-analysis/uiautodev-desktop-function.md)、[竞品运行验证](./research/uiauto-analysis/uiautodev-run-verification.md)、[ZCode 视觉基准](./research/design/zcode-client-design-spec.md) | 调研人 |
| 需求实现拆解 | [STORY.md](./STORY.md) | [story/](./story/) 目录 | RD |
| 环境配置与联调 | [env/](./env/) | [dev.md](./env/dev.md) | RD / 运维 |

## 给 Agent 的导航

- 想知道「产品要做什么」：`PRODUCT.md` → `feature/UI-LayoutSee需求文档PRD.md`
- 想知道「界面长什么样」：`DESIGN.md` → `designs/DESIGN.md`
- 想知道「竞品调研结论」：`RESEARCH.md` → `research/uiauto-analysis/`
- 想知道「某个需求怎么拆的」：`STORY.md` → `story/`
- 想知道「本地环境怎么搭」：`env/dev.md` → 对应 `source/<repo>/setup.md`

## 沉淀约定

- **人维护**：Agent 无法从代码读出的上下文（部署信息、设计原则、常见错误、分支规则）。
- **Agent 维护**：执行过程的产物且对后续任务有参考意义（如每个大 Feature 的开发记录），落到 `story/`。
- **不重复整理**：能从代码读出的 API 文档、编码规范不写进 docs。
