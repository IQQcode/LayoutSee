# DESIGN.md 视觉/UI 设计规范入口

LayoutSee 视觉与交互规范的入口文档。**单一事实源是 `designs/DESIGN.md`**，本文件只提供定位摘要与路由。

## 设计定位

**一个有 Apple 品质感、同时保持工具克制的开发者桌面工具。** 像 macOS 原生 App 一样安静，但能稳定承载画面、树、属性、诊断、配置和日志等高密度信息。

设计基调（详见设计系统文档）：

| 旋钮 | 数值 | 含义 |
|---|---:|---|
| `DESIGN_VARIANCE` | 4 | 结构稳定，允许局部不对称 |
| `MOTION_INTENSITY` | 3 | 只有悬停、反馈、状态切换和必要过渡 |
| `VISUAL_DENSITY` | 8 | 高密度工作台，依靠层级、对齐和分隔控制负荷 |

## 路由

- 设计系统与界面规范（单一事实源）：`./designs/DESIGN.md`
- 交互原型（页面跳转与行为）：`./designs/interaction-prototype.md`
- 新版界面截图（六张）：`./designs/redesign/`
- Stitch 设计输入（历史参考）：`./designs/stich-design.md`
- 视觉基准调研：`./research/design/zcode-client-design-spec.md`
- 产品上下文：`./PRODUCT.md`

## 冲突裁决

`designs/DESIGN.md` 为视觉与组件标准，`designs/interaction-prototype.md` 为行为标准，`designs/stich-design.md` 为历史设计输入。三者冲突时以前两者为准。
