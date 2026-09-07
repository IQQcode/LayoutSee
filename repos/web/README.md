# repos/web  web 端工程

LayoutSee Web 端正式工程（目标工程），基于 `source/layoutsee-prototype` 原型演进而来。

## 定位

- 承载 LayoutSee 工作台 UI 的正式实现：设备管理、群控、布局查看（常用 / 元素 / 插件 / MCP tab）、语义摘要、布局诊断、插件运行时。
- 构建产物供 `repos/mac` 桌面壳内嵌（WebView 渲染）。
- 视觉标准以 `docs/designs/DESIGN.md` 为单一事实源。

## 技术栈规划

- Vite 6 + React 19（与 prototype 同栈，代码可平滑迁移）。
- 依赖规划：`@hugeicons/react`（图标）、原生 CSS 或 CSS Modules（样式，对齐设计系统 token）。

## 目录结构（骨架）

```text
repos/web/
├── README.md          ← 本文件
├── src/               ← 界面代码
│   ├── pages/         ← 页面级组件（设备管理、群控、布局查看）
│   ├── components/    ← 可复用组件
│   └── styles/        ← 全局样式与设计 token
├── public/            ← 静态资源（图标、占位图）
└── tests/             ← 测试用例
```

## M0 初始化状态

- [x] 初始化根 workspace 与 `package.json`，锁定兼容 Node 20.14 的依赖版本。
- [x] 配置 `vite.config.mjs`，构建输出到 `dist/`。
- [x] 接入 `/api/v1/info` 的最小启动状态页。
- [ ] 从 `source/layoutsee-prototype/src` 迁移工作台页面骨架。
- [ ] 接入正式业务 API 与媒体通道；必须等待后续契约和 M0.5 风险验证关闭。

## 路由

- 原型参考：`../../source/layoutsee-prototype`
- 视觉规范：`../../docs/designs/DESIGN.md`
- 环境说明：`../../docs/env/dev.md`
