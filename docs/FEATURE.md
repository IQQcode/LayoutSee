---
name: Feature
description: >
  LayoutSee 需求说明：产品背景、目标用户、核心需求与 PRD 路由
---

# FEATURE.md 需求说明

LayoutSee 需求信息的入口文档。**单一事实源是 PRD**（`docs/feature/UI-LayoutSee需求文档PRD.md` v0.9），本文件提供背景摘要与路由，避免重复维护需求细节。

## 背景一句话

移动端 UI 调试缺一个「结构化视图感知层」：AI Agent 拿到的应是可推理的 View 树，而不是一张截图。现有竞品 UIAutoDev Desktop 验证了技术可行性，但主体闭源、License 受限、MCP 工具只是原子操作搬运、安全策略宽松，不适合直接采用。

LayoutSee 复用其开源内核的设备接入层做二次开发，重写产品层与 AI 适配层，目标成为「面向 Agent 的移动端运行时视图感知入口」。

## 核心需求域（详见 PRD）

1. **设备接入与工作台**：连接 Android / iOS / HarmonyOS 真机，实时投屏与操控。
2. **结构化视图感知**：抓取 UI 层级树，统一为 Node 契约，支撑元素定位与属性查看。
3. **语义化布局摘要**：面向 LLM 的低 token 结构描述，元素带 ref 可直接操作。
4. **布局异常诊断**：遮挡、重叠、越界、触控热区过小等问题的自动识别。
5. **MCP 服务**：以 SSE 按设备暴露工具给 AI 客户端。
6. **插件运行时**：HTML 插件扩展工作台能力（V1.0 范围）。
7. **团队能力（V1.0）**：鉴权、占用管理、审计。

## 路由

- 完整需求与验收标准：`./feature/UI-LayoutSee需求文档PRD.md`
- 产品上下文摘要：`./PRODUCT.md`
- 竞品调研：`./RESEARCH.md`
