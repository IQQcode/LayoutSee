# UIAutoDev 项目调研结论

## 1. 结论摘要

UIAutoDev 是一个“设备侧驱动 + 本地/服务端 API + 浏览器 UI”的移动端 UI 检查与自动化工具。核心目标不是在网页中直接解析手机画面，而是由 Python 客户端通过 ADB、uiautomator2、usbmux/WDA 或 Harmony HDC 获取原生 UI 层级，再把统一的 `Node` 树、截图和操作能力暴露给网页端。

项目当前形成两条产品形态：

- Python 客户端：默认监听 `127.0.0.1:20242`，启动后浏览器访问 `uiauto.dev`；网页资源通过本地 FastAPI 代理到线上站点，支持离线缓存。
- Desktop/Server：文档中描述的桌面版用于 scrcpy 投屏、DOM 树、插件、MCP 和多设备控制；Server 版是独立二进制，默认 33299 端口，面向远程访问和大规模设备管理。

核心实现是“控制面”和“媒体面”分离：HTTP API 负责设备列表、截图、层级树、命令和文件；WebSocket 负责 scrcpy/Harmony 实时画面与触控/按键双向流。网页端只是统一的交互壳，设备兼容性主要由本地驱动和系统工具链决定。

## 2. 代码结构与请求链路

### 2.1 入口与路由

- [app.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/app.py:37) 创建 FastAPI 应用，并挂载 Android、Android ADB、iOS、Harmony、Mock、XML 和资源代理路由。
- [cli.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/cli.py:147) 提供 `server`、`android`、`ios`、`shutdown` 等命令；无参数时默认启动 server。
- [router/device.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/router/device.py:20) 把 Provider/Driver 统一包装成设备 API，包括 `/list`、`/{serial}/screenshot/{id}`、`/{serial}/hierarchy`、tap、安装应用和当前应用。
- [router/xml.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/router/xml.py:14) 提供 XPath 校验接口，网页端可以在不重新访问设备的情况下检查 XML 和 XPath。

一次典型的“查看控件”流程是：

1. 浏览器请求 `/api/android/list`，Provider 通过 adbutils 枚举设备。
2. 用户选择设备后，请求 `/api/android/{serial}/screenshot/0` 和 `/api/android/{serial}/hierarchy`。
3. Driver 获取原始截图/XML，解析为统一 `Node` 树；网页端按 `bounds` 在截图上高亮节点，并展示 `properties`。
4. 用户点击屏幕或执行命令时，HTTP 请求回到 Driver；远程控制模式则升级为 scrcpy WebSocket。

### 2.2 统一数据模型

[model.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/model.py:31) 的 `Node` 是跨平台契约：

- `key`：按树索引拼接的稳定路径，如 `0-1-0`，同时可用于生成 XPath/定位路径。
- `name`：Android 通常是 class，iOS 是 `XCUIElementType*`，Harmony 是 JSON 节点类型。
- `bounds`：归一化坐标 `[left, top, right, bottom]`，便于不同屏幕尺寸和网页缩放下绘制。
- `rect`：Android 额外保留像素坐标和宽高，便于点击换算。
- `properties`：保留原始平台属性，避免统一模型丢失可定位字段。
- `children`：递归子树。

这个模型是桌面版、网页端、插件和 MCP 能共享的最小交集；它也使 Android XML、iOS WDA XML、Harmony JSON 可以被同一棵树形 UI 组件消费。

## 3. Android 布局抓取方案

### 3.1 两种 Driver

- `U2AndroidDriver` 是默认实现，通过 uiautomator2 服务执行 `dump_hierarchy()`、截图和点击。
- `ADBAndroidDriver` 是兼容实现，直接用 adbutils 调用 `uiautomator dump`、设备截图和 `input`/ADB 命令。环境变量 `UIAUTODEV_USE_ADB_DRIVER=1` 可切换。

代码见 [u2_driver.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/driver/android/u2_driver.py:20) 和 [adb_driver.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/driver/android/adb_driver.py:18)。ADB dump 遇到 `app_process` 冲突时会尝试杀掉相关进程后重试。

### 3.2 XML 到 Node

[common.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/driver/android/common.py:10) 使用标准库 XML 解析：

- `node@class` 作为节点名；根节点 `hierarchy` 原样保留。
- Android 的 `bounds="[x1,y1][x2,y2]"` 被解析为像素 `Rect`，同时除以窗口宽高生成归一化 `bounds`。
- `display-id` 可过滤多屏节点。
- 子节点索引递归生成 `key`，这是当前项目最直接的树路径标识。

因此网页端不依赖 Android 专属 XML 结构，只依赖 `Node`。XPath 校验仍在服务端用原始 XML 完成，避免从 JSON 树反向重建 XML。

### 3.3 Android 实时画面和输入

[scrcpy.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/remote/scrcpy.py:90) 会把内置 `scrcpy-server-v2.7.jar` 推到设备，通过 ADB local abstract socket 建立视频和控制连接：

- 视频 socket 的 H.264 数据以 WebSocket 二进制帧转给浏览器。
- 控制 socket 接收 `touchDown/touchMove/touchUp/keyEvent/text/ping` 等 JSON 消息。
- 触控坐标使用网页传来的比例值 `xP/yP` 乘以设备分辨率，天然适配浏览器缩放和不同屏幕尺寸。
- [scrcpy3.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/remote/scrcpy3.py:11) 针对 3.3.3 使用双工 pipe，把视频与控制协议透传给前端 WebCodec 解析。

这说明“网页端投屏”不是截图轮询，而是浏览器持续消费二进制媒体流；“布局查看”仍是独立的 HTTP XML/JSON 请求。

## 4. iOS 布局抓取方案

### 4.1 WDA + usbmux

[ios.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/driver/ios.py:23) 以 UDID 创建 `wdapy.AppiumUSBClient`，底层通过 usbmux 把电脑请求转发到设备 8100 端口的 WebDriverAgent：

- `screenshot()` 和 `window_size()` 由 WDA 客户端提供。
- `sourcetree()` 获取 XCTest XML 层级树。
- `tap()`、home、音量等操作通过 WDA 执行。

语雀文档补充了运行前置条件：设备需挂载 Developer Disk Image、电脑需运行 usbmuxd、设备需安装已签名的 WDA；iOS 17+ 还需启动 `ios tunnel start --userspace`。若 `/status` 不可访问，桌面/服务端会尝试执行 `ios launch com.facebook.WebDriverAgentRunner.xctrunner`。

### 4.2 XCTest XML 到 Node

`parse_xml_element()` 递归读取 `XCUIElementTypeApplication`、`type`、`name`、`label`、`visible`、`x/y/width/height` 等属性：

- `visible=false` 节点被过滤。
- Application 根节点提供真实窗口宽高。
- 坐标由像素矩形换算为归一化四元组，属性原样放入 `properties`。
- 节点名使用 `type`，例如 `XCUIElementTypeCell`、`XCUIElementTypeStaticText`。

Android 和 iOS 的统一点是“原生层级 XML + 归一化 bounds + 属性字典”；差异是 Android 额外保留 `Rect`，iOS 的定位属性更多依赖 `name/label/value/identifier/traits`。

### 4.3 iOS 的稳定性边界

iOS 抓取链路明显依赖外部服务状态，不是单个 Python 进程可以完全兜底：WDA 签名、Developer Disk Image、usbmuxd、iOS 17+ tunnel 任一环节失败，设备可能能被枚举但没有画面或层级树。研究时应把这些作为“接入诊断项”，而不是归因于网页 UI 缺陷。

## 5. 桌面端与网页端适配

### 5.1 Python 客户端网页模式

[router/proxy.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/router/proxy.py:15) 将 `/`、`/android/*`、`/ios/*`、`/assets/*` 等请求代理到 `https://uiauto.dev`，并可在 `--offline` 下将 GET 响应缓存到 `./cache/http`。启动线程等待本地 `/api/info` 成功后打开网页。

浏览器与本地客户端通过两类通道连接：

- HTTP：设备列表、截图、层级、命令、OCR、XPath 校验、应用安装/备份。
- WebSocket：Android scrcpy、Harmony MJPEG、代理 WebSocket。

Chrome 插件是另一种桌面适配方式。`manifest.json` 允许 `app-inspector.devsleep.com` 和 localhost 外部通信；[background.js](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/chrome_plugin/background.js:15) 把网页消息转发到 `http://localhost:20242`，JSON 原样返回，图片等非 JSON 数据转成 Base64。

### 5.2 Desktop/Server 形态

语雀 Desktop 文档明确列出：scrcpy 控制手机、DOM 树、HTML 插件、MCP、多设备控制；Server 文档则说明独立二进制、默认 33299、浏览器直接访问、500 台以上设备管理。可以推断 Desktop/Server 复用了同一套协议和 UI 能力，但把 Python 客户端的本地进程包装成跨平台桌面/服务端发行物。

### 5.3 插件与 MCP

插件使用 HTML 编写，通过 iframe 嵌入设备控制页；目录通常为 `plugins/<id>/index.html` 与必需的 `plugin.json`。运行时会注入 `/plugins/:plugin-id/__runtime.js`，插件可获得 `deviceId`、版本信息并调用 `$u.shell()` 等开放 API。这个设计把设备能力作为稳定的 JavaScript API 暴露给桌面网页，同时保留 iframe 隔离。

MCP 是同一 API 的 AI 适配层。Desktop 页面截图中可见每台设备生成 SSE MCP 地址；Server/桌面文档也把 MCP 列为内置能力。因此布局树、截图、tap、shell 等能力可以被 AI 客户端当作工具调用，而不必直接理解 ADB/WDA。

## 6. 适配评价与风险

### 优点

- 统一 `Node` 契约屏蔽 Android/iOS/Harmony 原始树差异。
- `bounds` 归一化 + scrcpy 比例坐标同时适配窗口缩放、横竖屏和多种设备尺寸。
- HTTP 控制面与 WebSocket 媒体面分离，便于网页、桌面、插件和 MCP 复用。
- MockProvider 和 XML parser 单测使没有真机时仍能验证部分行为。
- 离线缓存和 Chrome 外部消息通道解决了本地服务与线上网页的跨进程连接问题。

### 风险和改进建议

1. [app.py](/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev/uiautodev/app.py:39) 使用 `allow_origins=["*"]` 同时开启凭据，服务端暴露到公网时应收紧来源、鉴权和 CSRF 策略。
2. 插件与 shell API 能力很强，远程 Server 必须增加设备级授权、插件信任边界、命令审计和速率限制。
3. `proxy.py` 的缓存键主要按 URL 计算，部署多用户服务时应明确缓存隔离和敏感响应禁止缓存规则。
4. iOS 的自动化前置依赖多，建议在 `/api/info` 或设备诊断接口中显式返回 WDA、tunnel、Developer Disk Image 状态。
5. Android 与 iOS 的节点属性没有版本化 schema；建议增加 `platform`、`source`、`window_size` 和 schema version，降低网页端兼容成本。
6. 归一化坐标依赖抓取时窗口尺寸；旋转、刘海/安全区、辅助功能缩放变化后应让前端重新获取 window size，避免点击偏移。

## 7. 推荐的二次开发落地方案

若要把该项目改造成稳定的内部平台，建议按以下边界演进：设备接入层保留现有 Driver；增加一个明确的 `LayoutSnapshot`（设备、平台、方向、窗口尺寸、时间戳、树）；API 层统一鉴权和错误码；网页端把截图、树和操作抽象为协议；Desktop/Server 只负责发行、进程管理和权限策略；插件/MCP 只依赖协议，不直接依赖 ADB/WDA。

这样可以继续复用现有 Android/iOS 驱动，同时让桌面端、纯网页端、远程 Server 和 AI 工具在同一份布局快照和操作协议上演进。

## 8. 调研来源

- GitHub：<https://github.com/codeskyblue/uiautodev>
- Desktop 文档：<https://www.yuque.com/codeskyblue/uiautodev/desktop>
- Server 文档：<https://www.yuque.com/codeskyblue/uiautodev/server>
- Python 使用文档：<https://www.yuque.com/codeskyblue/uiautodev/usage>
- 插件系统：<https://www.yuque.com/codeskyblue/uiautodev/plugin>
- iOS 问题与诊断：<https://www.yuque.com/codeskyblue/uiautodev/ga0iixeo5euhfq3e>
- iOS 手工流程：<https://www.yuque.com/codeskyblue/uiautodev/ios-automation-manual>
- 项目介绍页：<https://uiauto2.devsleep.com/>
