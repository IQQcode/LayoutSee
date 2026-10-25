# iOS 布局抓取接入 Lookin 评估

> 调研日期：2026-10-25。目标：评估 LayoutSee 内置接入开源工具 Lookin 实现 iOS 布局抓取的成本与改动点，不做从零自研。

## 一句话结论

**可行，推荐「Core 内纯 Python 复刻 Lookin 客户端协议」路线，估算 1.5～2.5 人周（不含 HarmonyOS）**；不建议直接把 Lookin 的 macOS 客户端代码嵌进产品（GPL-3.0 传染 + 原生构建链成本）。接入前必须先接受一个产品级差异：**Lookin 模式下 iOS 只能抓「集成了 LookinServer SDK 的自家 App」（Debug 构建），抓不了任意三方 App**——这与 Android 端 uiautomator 可抓任意 App 是本质区别。

## Lookin 工作原理（与接入直接相关的部分）

Lookin 是 Reveal 的开源替代，双端结构：

- **被测端**：[QMUI/LookinServer](https://github.com/QMUI/LookinServer)（iOS SDK，v1.2.8）。被测 App 通过 CocoaPods `pod 'LookinServer', :configurations => ['Debug']` 或 SPM 集成，**官方明确警告不得进 Release 配置**。
- **客户端**：[hughkli/Lookin](https://github.com/hughkli/Lookin)（macOS App，ObjC）。LayoutSee 要替换的就是这一端。

通信机制（已读源码确认）：

| 层 | 事实 |
|---|---|
| 传输 | PeerTalk 协议（rsms/PeerTalk，MIT）。USB 真机走 usbmuxd 隧道（PeerTalk 约定连设备 2345 端口的 hub，再以虚拟端口 47175–47179 与 LookinServer 互通）；模拟器走本机 loopback TCP 47164–47169 |
| 载荷 | **NSKeyedArchiver**（二进制 plist）归档 LookinShared 对象图，非 protobuf |
| 握手 | 先 Ping（0.5s 超时）→ 校验 LookinServer 版本（客户端 1.2.x 仅接受 server version = 7）→ 再发真正请求，超时 5s |
| 请求类型 | `LookinDefines.h` 枚举：Ping=200、App=201、Hierarchy=202、HierarchyDetails=203、AllAttrGroups=210、FetchObject=207、FetchImageViewImage=208、InvokeMethod=206、AttrModification 等 |
| 刷新耗时 | 官方文档：500 个 view 的层级+属性 ~1s；含双份截图（每个 view 的 Solo/Group 截图）时 3～10s、几十 MB。**不传图像则 <0.3s** |
| 能力边界 | 可读层级/属性/截图、可改属性（AttrModification）；**没有 tap/输入注入能力** |

共享协议模型（`Src/Main/Shared/**`：LookinObject、LookinAttributesGroup、LookinDisplayItem、LookinAppInfo、LookinConnectionAttachment 等 ~25 个类）与被测端同仓库。

## License 状况（接入路线的决定因素）

| 仓库 | LICENSE | 说明 |
|---|---|---|
| hughkli/Lookin（mac 客户端） | **GPL-3.0**（LICENSE 原文确认） | 复制/链接其代码会传染 GPL，LayoutSee 目前无 LICENSE（默认保留所有权利），嵌入即产生分发义务 |
| QMUI/LookinServer（iOS SDK + LookinShared 协议层） | **MIT**（LICENSE 原文确认，Copyright 2023 LI KAI） | ⚠️ 仓库内两个 podspec 元数据仍写 `GPL-3.0`，与 LICENSE 文件矛盾，以 LICENSE 为准但此歧义需留痕 |
| rsms/PeerTalk | MIT | 帧协议格式可参考 |
| xiaoxiaowesley/lookin-mcp-peertalk | 无 LICENSE（默认保留权利） | TypeScript 完整实现了 PeerTalk + Lookin 协议客户端（list_devices/list_apps/hierarchy 等 6 个 MCP 工具），**代码不可抄，但证明第三方复刻协议完全可行**，是最佳可行性佐证与协议参照 |

## 路线对比

### 路线 A：Core 内纯 Python 复刻客户端协议（推荐）

在 `repos/core` 新增 iOS 设备驱动层，与 `adb.py`/`media.py` 并列：

- `usbmux.py`：纯 socket 连 `/var/run/usbmuxd`，plist 协议做设备枚举与 Connect 隧道（~250 行）。
- `lookin.py`：PeerTalk 帧编解码（PTNI magic + type + tag + length，~150 行）+ NSKeyedArchiver 编解码（Python `plistlib` 解 `$objects` 结构或用 `bpylist2`，自写 Lookin 类还原器，~500 行）+ 请求编排与版本握手（~200 行）+ Lookin 树 → LayoutNode 适配（~400 行）。
- 完全符合仓库既有约束：Mimosa hook 要求新代码网络用纯 socket、子进程收敛（本路线零子进程、零原生依赖，PyInstaller 打包链零变化）；License 干净（只依据 MIT 的 LookinShared 源码理解协议结构，自写实现，不搬 GPL 代码）。

**成本：协议层 3–5 天 + 集成 2–3 天**。风险集中在对 NSKeyedArchiver 对象图的逆向理解，用真机抓包落 fixture 金样（参照 `test_session_token` 的 Node/Python 金样模式）控制回归。

### 路线 B：基于 LookinShared 写精简 ObjC/Swift helper 随包分发

用 MIT 的 LookinShared + PeerTalk 写一个只含连接层的 CLI（避开 GPL 的 LookinClient 代码），打包进 DMG，Core 以 argv 列表子进程调用（收敛到一个 `LookinClient` 类，模式上可接受）。协议保真度最高，但给纯 Python + Electron 的打包链引入 Xcode target / CocoaPods / 双架构二进制，构建与 CI 成本实际高于路线 A。**不推荐首选**，若路线 A 在对象图还原上反复受挫，可作为 B 计划。

### 路线 C（对照项，非本次范围）：WebDriverAgent 抓任意 App

WDA 无需被测 App 做任何集成、可抓任意前台 App 的 a11y 树（精度与 Android uiautomator dump 对齐）、协议是 HTTP/JSON 简单得多；但需要解决 WDA App 的签名/安装/开发者模式（免费证书 7 天过期），且拿不到 UIKit 级细节（字体、颜色、内边距），也没有截图渲染链。**建议记入 backlog 作为「任意 App」能力的二期选项**，与 Lookin（自家 App、UIKit 级细节）互补。

## LayoutSee 改动点清单

| 工程 | 改动 | 说明 |
|---|---|---|
| `repos/contracts` | `schemas/device/device.json`：`platform` enum 增加 `"ios"`；`deviceId` 约定 `ios-{udid}` | capabilities 复用 `screenshot`/`layout`；`input`/`apps` 对 iOS 暂不下发 |
| `repos/core` | 新增 `usbmux.py`、`lookin.py`；`devices.py` DeviceRegistry 并行接 usbmux 轮询（5s 周期与 adb 一致）；iOS 设备默认 readonly（Lookin 无注入能力，天然贴合现有只读门禁） | `device_id_for` 按 platform 分派 |
| `repos/core` | `snapshots.py`：iOS 抓取 = Hierarchy + AllAttrGroups → 适配为现有 LayoutNode；**生成等价 XML** 供 `xpath.py`/`selectors.py`（它们只查快照 XML）；context_changed 比对逻辑复用 | `diagnostics`/`summary`/`finder` 是纯函数，理论上零改动复用，补 iOS 语义映射单测即可 |
| `repos/core` | `media.py` 不动：iOS 无 scrcpy 等价物，v1 不做实时投屏 | 后期截图可用 pymobiledevice3（纯 Python，lockdown 截图服务）补 |
| `repos/web` | `DevicesPage.jsx`：iOS Tab 从 `PlatformPlaceholder` 切真列表；空态引导文案改为 LookinServer 集成三步（pod 集成 → Debug 运行 → USB 连接） | 平台 Tab 骨架已存在 |
| `repos/web` | `WorkbenchPage`/`DeviceCanvas`：iOS 默认 snapshot 模式（live 仅 Android），canvas v1 用 wireframe 骨架渲染（`.node-overlay.wireframe` 已有样式）——首次只拉层级+属性（<1s），不拉截图 | 能力位由 `capabilities` 驱动，勿做平台嗅探 |
| `repos/web` | `CommonTab`（包管理/启停）与终端卡片对 iOS 隐藏（adb 专属）；插件平台过滤机制已有 | `ElementTab`/`McpTab`/`IntelligenceTab` 基本不动 |
| `repos/mac` | **无改动** | 设备逻辑全在 Core，纯 Python 依赖不影响 PyInstaller/electron-builder |
| 契约回填 | openapi 无新端点（设备/快照接口全复用），`contracts:check` 门禁跑通即可 | |

## 风险与待真机验证清单

1. **LookinServer 1.2.8 在新 iOS 上的可用性**（最高风险）：上游最后提交 2024-07，issue 区 2025–2026 年大量「不能用/崩溃/内存被杀」反馈（#57 内存超限被系统杀、#61/#59 层级崩溃、#56/#53 发现不了 App）。但 2026 年社区仍活跃：PickView fork（加无线+Flutter 调试）、lookin-mcp-peertalk（2026-05 发布）。**P0：找一台目标 iOS 版本真机 + LookinDemo 冒烟，能抓到层级即 go**。
2. **版本耦合**：客户端与 LookinServer 有严格版本区间校验（当前 =7）。我们 pin LookinServer 1.2.8 即可自洽，但上游无修复意味着遇到 iOS 兼容问题只能自己 fork LookinServer（它是 MIT，fork 合规）。
3. **刷新性能**：含截图的完整抓取 3–10s；v1 只拉层级+属性可压到亚秒级，把「重抓取」设计为显式动作（现有 CaptureCoordinator 原子抓取模型可承接）。
4. **License 留痕**：LookinShared 的 podspec 标 GPL-3.0 与 LICENSE 文件 MIT 矛盾——自写实现按「只读协议结构、不搬运代码」的 clean room 方式做，并在实现文件头注明协议事实源为 QMUI/LookinServer（MIT）。

## 工作量汇总

| 阶段 | 内容 | 估算 |
|---|---|---|
| P0 冒烟 | 真机 + LookinDemo 跑通抓取，确认目标 iOS 版本可用 | 0.5–1 天 |
| 协议层 | usbmux + PeerTalk 帧 + NSKeyedArchiver 编解码 + 对象模型（含 fixture 金样测试） | 3–5 天 |
| Core 集成 | 设备注册、快照适配、XML 生成、readonly、MCP 工具回归 | 2–3 天 |
| Web | 设备页 iOS Tab、工作台降级、引导文案 | 1–2 天 |
| 契约与测试 | device.json 契约、契约测试、单测 | 1 天 |
| **合计** | | **约 1.5–2.5 人周** |
