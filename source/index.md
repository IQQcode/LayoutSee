# source 说明索引

LayoutSee Workspace 的仓库说明入口。`source/` 只放说明，代码本体在 `repos/`（本工程源代码）与本目录下的参考工程中。

## 本工程源代码（repos/）

| 工程 | 定位 | 技术栈 | 状态 |
|------|------|--------|------|
| [repos/contracts](../repos/contracts/) | 跨进程协议与生成模型的单一事实源 | OpenAPI 3.1 + JSON Schema 2020-12 | 已初始化，[说明](./contracts/overview.md) |
| [repos/core](../repos/core/) | 第一方本地 Core 与可控测试替身 | Python 3.12 + Pydantic 2 + elementpath | 设备/快照/XPath/摘要/诊断/MCP 主链路可用，[说明](./core/overview.md) |
| [repos/web](../repos/web/) | LayoutSee Web 端正式工程（工作台 UI），从 prototype 演进 | Vite 6 + React 19 + Phosphor | 设备页/群控/五 Tab 工作台/设置已实现，[说明](./web/overview.md) |
| [repos/mac](../repos/mac/) | LayoutSee macOS 桌面壳（窗口、进程守护、发行），内嵌 web 构建产物 | Electron 44 + electron-builder 26 | arm64 本地候选包已构建，待人工测试，[说明](./mac/overview.md) |
| [repos/plugins](../repos/plugins/) | 随包发行的插件包（iframe UI + 声明式 Core 贡献），无构建步骤 | 原生 HTML/CSS/JS + manifest v2 | 内置示例与 Android 日志抓取已落地，[说明](./plugins/overview.md) |

## 参考与原型工程

三件套说明与代码同放一处，便于就近查阅。

| 工程 | 定位 | 说明位置 | 语言/技术栈 |
|------|------|---------|------------|
| layoutsee-prototype | LayoutSee 前端原型（工作台 UI 与交互验证） | [overview](./layoutsee-prototype/overview.md) / [setup](./layoutsee-prototype/setup.md) / [test](./layoutsee-prototype/test.md) | Vite 6 + React 19 |
| uiautodev | 第三方开源内核（竞品），设备接入层参考与复用 | [overview](./uiautodev/overview.md) / [setup](./uiautodev/setup.md) / [test](./uiautodev/test.md) | Python 3（Poetry） |

> uiautodev 是上游 git 仓库，三件套已写入其 `.git/info/exclude`，不会污染上游工作区。

## 三件套说明

- **overview.md**：这个仓库是什么、对外提供什么能力、对内依赖什么模块。
- **setup.md**：如何 Build、如何启动 / Debug。
- **test.md**：如何测试、如何写测试用例。

> 新增本工程模块时：在 `repos/` 落代码，在本目录登记并补三件套。引入外部参考工程时：代码放 `source/<repo>/`，三件套与代码同放。
