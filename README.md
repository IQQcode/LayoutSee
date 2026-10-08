<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/readme/logo-dark.png">
    <img src="./assets/readme/logo-light.png" width="240" alt="LayoutSee">
  </picture>
</p>

<h1 align="center">让 Agent 感知视图，触摸界面。</h1>

<p align="center">把 Android 真机上的视图树，变成 Agent 可读、可定位、可操作的结构。</p>

<p align="center">
  中文 · <a href="./README.en.md">English</a><br>
  <a href="#开始使用">开始使用</a> · <a href="#交给-agent">交给 Agent</a> · <a href="#从源码运行">从源码运行</a>
</p>

<p align="center">
  <img src="./assets/readme/hero-inspector.webp" width="100%" alt="LayoutSee 工作台：手机画面、控件属性与视图树联动，选中元素的边界在画面中高亮">
</p>

**截图让 Agent 看见画面，LayoutSee 让它接触画面背后的真实视图。**

LayoutSee 是面向移动端开发者、QA 与 AI Agent 的 macOS 工具。通过 MCP，把 Android 运行时视图树交给 Agent：控件是什么、在哪、多大、属于谁、能不能点，都有结构依据。再沿着定位结果点击、滑动、输入，让分析接上真实操作。

> 从「这里像一个按钮」，到「找到这个控件，读出它的边界，点击后验证页面」。

## 它让 Agent 多了什么

1. **感知：读懂界面的结构。** 文本、resource-id、父子层级、边界与交互属性一起读取。截图保留视觉上下文，View 树提供结构证据。
2. **定位：找到具体的控件。** 按文本、描述、resource-id 或 XPath 查找，拿到短引用 `ref`，把一句「点登录」落到当前快照里的元素。
3. **触摸：对真机采取行动。** 用 `tap`、`swipe`、`input_text` 操作设备，再抓取新快照验证结果。只读模式与操作审计让过程可控。
4. **诊断：让问题有据可查。** 检查重叠、遮挡、越界、触控热区过小、文本截断和隐形可交互，返回涉及的节点与量化证据，供 Agent 继续分析。

## 从看见，到动手

**抓取页面 → 读取结构 → 定位元素 → 操作设备 → 再次验证。**

一次快照关联画面、层级、属性与坐标，尽力保持同步；语义摘要把它压缩为便于 Agent 阅读的元素清单，每项带 `ref` 与归一化边界。无需先读完整 XML，就能了解页面骨架，再按需深入。

<p align="center">
  <img src="./assets/readme/summary.webp" width="100%" alt="布局智能面板：带 ref 与坐标的语义摘要，以及六类布局诊断入口">
</p>

人也能沿着同一份结构检查：点画面，树上定位；选节点，画面高亮。属性面板、XPath 查询与带命中数的候选选择器，让控件从「看得到」变成「查得清」。

## 开始使用

当前支持 **macOS + Android 真机**。iOS 与 HarmonyOS 仍为界面预览，尚未接入。

1. 在 [Releases](https://github.com/IQQcode/LayoutSee/releases/latest) 下载 DMG：Apple Silicon 选 `arm64`，Intel 选 `x64`。也可[从源码运行](#从源码运行)。未签名包首次打开若被拦截，在「系统设置 → 隐私与安全性」中选择「仍要打开」。
2. 开启手机的开发者选项与 USB 调试，用支持数据传输的数据线连接 Mac，在手机上确认调试授权。
3. 打开设备工作台，操作手机画面，或抓取快照查看视图树。

设备接入依赖 `adb`，可在设置中指定路径，或先安装：

```bash
brew install android-platform-tools
```

## 交给 Agent

在设备工作台的 **MCP** Tab 复制配置，粘贴到支持 MCP 的客户端。每台在线设备都有独立端点；实际地址以界面给出的配置为准。

<p align="center">
  <img src="./assets/readme/mcp.webp" width="100%" alt="MCP 面板：按设备提供端点、可复制的客户端配置与工具列表">
</p>

再把 [`layout-see` Skill](./skills/layout-see/) 交给 Agent，告诉它任务，例如：

- 「读取当前页面，列出可点击元素及其 resource-id。」
- 「检查底部按钮的边界和点击区域，看看有没有遮挡证据。」
- 「找到登录入口并点击，再抓取页面确认是否进入登录页。」
- 「输入搜索词并提交，检查结果页的控件结构。」

Agent 根据任务调用工具：

| 目的 | MCP 工具 |
| --- | --- |
| 感知页面 | `capture_layout` · `get_layout` · `get_layout_summary` |
| 定位控件 | `find_element` · `query_xpath` |
| 检查布局 | `diagnose_layout` |
| 操作真机 | `tap` · `swipe` · `input_text` |
| 补充上下文 | `get_device_info` · `get_current_app` · `get_screenshot` |

共 12 个内置工具，9 读 3 写。开启只读模式后，写操作会被拦截；页面变化后应重新抓取，使用新快照中的 `ref`。按 `ref` 点击时，工具使用该节点边界的中心坐标。完整调用方式见 [Skill 工具说明](./skills/layout-see/references/mcp-tools.md)。

## 也给开发者一张工作台

投屏与操控、视图树与属性、XPath 与选择器、布局摘要与诊断，在一个窗口里完成。还可通过插件接入日志抓取、快照速览，或扩展工作台与 MCP 工具。

<details>
<summary>查看工作台与日志插件</summary>

<p align="center">
  <img src="./assets/readme/workbench.webp" width="100%" alt="设备工作台：手机画面、设备控制栏与应用操作面板">
</p>

<p align="center">
  <img src="./assets/readme/logcat.webp" width="100%" alt="Android 日志抓取插件：级别、tag 与 pid 过滤，支持暂停和自动滚动">
</p>

插件示例见 [`repos/plugins`](./repos/plugins/)，架构与扩展方式见 [插件说明](./source/plugins/overview.md)。

</details>

## 感知的边界

- **结构来自设备暴露的节点。** WebView、自绘 Canvas 的内部元素可能缺失；此时用截图补充视觉信息，无法据此证明内部层级或 resource-id。
- **快照对应一次采集。** 抓取期间页面跳变时需重新采集；几何诊断提供排查线索，具体原因仍需结合截图与源码确认。
- **设备处理在本地完成。** Core 默认监听回环地址；接入外部 AI 客户端后，数据如何发送由该客户端配置决定。

快照存档与 diff、离线导入导出、Windows 和团队服务仍在规划中，见 [PRD](./docs/feature/UI-LayoutSee需求文档PRD.md)。

## 从源码运行

需要 macOS、Node ≥ 22.12、Python 3.12、`uv` 与 `adb`。

```bash
git clone https://github.com/IQQcode/LayoutSee.git
cd LayoutSee
npm install
npm run dev:web      # 启动本地 Core 与 Web 工作台
```

```bash
npm run test:unit    # 单元测试
npm run lint         # 静态检查
npm run build:all    # 契约检查与构建
npm run package:mac  # 打包 macOS 应用
```

工程入口与构建说明见 [source/index.md](./source/index.md)，完整工作区导航见 [docs/repo-structure.md](./docs/repo-structure.md)。

## 致谢

Android 设备接入与投屏能力基于 [uiautomator2](https://github.com/openatx/uiautomator2)、[scrcpy](https://github.com/Genymobile/scrcpy) 等开源项目；设备接入层参考并二次开发自 [uiautodev](https://github.com/codeskyblue/uiautodev)。
