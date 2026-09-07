# web 工程说明

`repos/web` 是 LayoutSee 正式工作台 UI（React 19 + Vite 6 + react-router 7 + Phosphor），构建产物由 Core 同源托管。业务数据全部来自版本化 HTTP 契约，不内置静态假数据。

页面与路由：

| 路径 | 页面 |
|---|---|
| `/devices` | 设备管理（5 秒增量刷新、复制序列号、接入诊断、多选进入群控、三步接入引导、ADB 缺失引导） |
| `/group` | 群控预览（多路截图轮询、超阈值降频提示、单格冻结、双击进工作台） |
| `/devices/:deviceId/workbench/:tab` | 设备工作台（控制轨 + 画面 + 任务面板，Tab 只替换右侧面板） |
| `/settings` | 外观 / 设备与驱动 / 投屏 / 安全 / 关于 |

工作台 Tab：常用（前台应用、启动、停止确认、包管理：系统应用开关 / 清除数据 / 卸载）、元素查看（快照抓取、层级树与属性面板联动、XPath 查询与选择器、命中序号切换）、终端（自由输入 adb shell 命令，历史与高危二次确认）、MCP（运行时工具目录与四客户端配置）、插件（清单列表、打开目录）、布局智能（语义摘要 + 六类诊断）。

宿主：Electron 壳与浏览器共用同一套构建产物，差异全部收敛到 `src/app/HostBridge.js` 的 `kind` 与 `can` 能力清单，不做环境嗅探分叉。浏览器下会话令牌由 Core 注入首页 meta，只支持 loopback 访问。

关键机制：

- URL 是页面/设备/Tab 的可恢复状态源；刷新走 Core SPA 回退，`Cmd+[` 与 History 一致。
- 切 Tab 不重挂画面、不重连媒体、不清快照；切设备保留 Tab 但清理旧上下文。
- 画面为截图轮询模式并明确标识；单击 tap、拖拽 swipe、中键 Home、右键 Back、滚轮滑动、键盘输入。
- 审查模式点击选择节点；冻结保持最后一帧；只读模式同时禁用 UI 写入口与服务端执行。
- 双层分隔条：一级 330–720px 设备区，二级属性面板；方向键 12px、Shift 32px、Home/End、双击复位，宽度按设备持久化。
- 工作台底部常驻状态栏：设备物理分辨率、鼠标像素坐标与百分比、当前快照节点数、Core 版本。
- 主题 Token 来自 DESIGN.md，浅色/深色/跟随系统，`prefers-reduced-motion` 关闭位移动效。

## 模块

```text
src/app/            AppShell、路由桥、主题、错误边界、HostBridge（宿主能力清单 + 会话初始化）
src/api/client.js   envelope 客户端 + 会话令牌注入 + 全部契约端点
src/components/     按钮、状态、横幅、弹窗、Toast、分隔条等可访问组件
src/features/       devices / group-preview / workbench（含 terminal Tab）/ settings / plugins
src/media/          （预留；实时媒体解码属后续 Story）
src/styles/         tokens.css（语义 Token）与 app.css（组件样式）
```
