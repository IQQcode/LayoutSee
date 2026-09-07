---
name: Research
description: >
  LayoutSee 调研说明：竞品架构、功能清单、运行验证与视觉基准的索引
---

# RESEARCH.md 调研说明

LayoutSee 调研内容的入口文档。调研是 PRD 的重要输入，本文件提供结论摘要与路由。

## 调研结论摘要

| 主题 | 结论 | 详细文档 |
|------|------|---------|
| 竞品架构调研 | UIAutoDev Desktop 通过 ADB / uiautomator2 / WDA / HDC 拿原生层级，统一为 Node 树，经 HTTP 控制面 + WebSocket 媒体面暴露；但主体闭源、License 受限 | [uiautodev-analysis.md](./research/uiauto-analysis/uiautodev-analysis.md) |
| 竞品功能清单 | 覆盖设备管理、布局抓取、元素查看、插件、MCP 工具等；MCP 工具只是原子操作搬运，缺少语义压缩与诊断 | [uiautodev-desktop-function.md](./research/uiauto-analysis/uiautodev-desktop-function.md) |
| 竞品运行验证 | 本地运行链路验证（内核服务、HTTP/WS 端口、SSE MCP），确认技术可行性；安全策略宽松（allow_origins=*），不适合直接暴露 | [uiautodev-run-verification.md](./research/uiauto-analysis/uiautodev-run-verification.md) |
| 视觉基准 | ZCode 客户端视觉规范作为 LayoutSee 的视觉设计基准 | [zcode-client-design-spec.md](./research/design/zcode-client-design-spec.md) |

## 调研结论对产品的三个影响

1. **技术路线**：复用 uiautodev 开源 Python 内核（`source/uiautodev`）的设备接入层做二次开发。
2. **产品差异化**：重写产品层与 AI 适配层，MCP 工具面向 Agent 做语义压缩与诊断，而非原子操作搬运。
3. **安全设计**：收紧服务端策略（CORS、插件 shell 能力审计），可安全暴露。

## 路由

- 竞品界面截图：`../assets/pic/`（01 至 06）
- 参考源码：`../source/uiautodev`
- 需求文档：`./feature/UI-LayoutSee需求文档PRD.md`
