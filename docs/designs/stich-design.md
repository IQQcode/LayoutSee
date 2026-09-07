---
name: stich-design
description: >
  LayoutSee（macOS 桌面应用）视觉设计规范：设计语言 + Token 体系 + 布局骨架 + 页面与组件规范。
  stich 创作步骤：
  1. 确定设计体系（阅读第二、三、四章，先定 token 再画页面）；
  2. 生成产品页面（按第五、六章骨架与页面结构逐页产出）；
  3. 局部调整细节（按第十章检查清单自检收敛）。
  工程化 token 对齐 zcode-client-design-spec.md，质感与排版语言对齐 apple.com 参考风格，
  页面结构与交互以 docs/designs/redesign 新版原型和 interaction-prototype.md 为准。
---

# LayoutSee 视觉设计规范（stich-design）

> 版本：v0.2（对齐新版原型）｜ 日期：2026-08-26 ｜ 适配终端：macOS App（原生壳 + 内嵌 Web UI）
> 关联文档：[交互原型文档](./interaction-prototype.md)、[PRD](../feature/UI-LayoutSee需求文档PRD.md)、[ZCode 客户端设计规范（token 基准）](../research/design/zcode-client-design-spec.md)
> 界面依据：[新版原型 01–06](./redesign/)（本规范唯一视觉依据）；旧版竞品截图 `assets/pic/` 仅作功能对照，不再作为视觉依据

## 参考内容

- **视觉依据**：`docs/designs/redesign/` 01–06 新版原型。页面结构、区域比例、控件形态、Tab 顺序、表格列序一律以原型为准。
- **设计风格参考**：https://www.apple.com/za/ ，只取「设计语言」：SF Pro 排版质感、大量留白的区块式布局、克制的高亮与光效、深浅主题无缝切换、平滑微动效；不取「营销叙事」：无 Hero 大图、无滚动视差、无渐变卖点区。
- **Token 基准**：[zcode-client-design-spec.md](../research/design/zcode-client-design-spec.md)，即中性色阶 + 单一强调色 + 深浅双主题 + 4pt 栅格，LayoutSee 在它的语义结构上叠加 Apple 质感，两者冲突时以本规范为准。
- **功能语义**：[竞品功能梳理](../research/uiauto-analysis/uiautodev-desktop-function.md) 与 [运行验证](../research/uiauto-analysis/uiautodev-run-verification.md)，用于确定控件的行为含义（按键注入、原子抓取、XPath 查询、MCP 端点、插件运行时）。

## 一、产品描述

### 它是什么

LayoutSee 是一款面向移动开发与 AI 协同场景的 macOS 桌面应用：连接 Android / iOS / HarmonyOS 真机，实时投屏操控，抓取结构化 UI 层级树（布局快照），提供语义摘要、布局异常诊断与 MCP 服务，把「移动设备运行时视图」变成 AI Agent 可读、可定位、可操作的结构化资源。

视觉定位一句话：**一个有 Apple 品质感、但保持工具克制的开发者桌面工具**，像 macOS 原生 App 一样安静，同时承载比普通工具高得多的信息密度（画面、树、属性、诊断）。

### 为什么做它

1. AI Agent 验证移动端界面时只能「截图 + 猜」：截图丢失 resource-id、text、bounds、可点击性等确定性属性；视觉判断回答不了「按钮多大、在哪、是否被遮挡」；每轮判断消耗大量图像 token。
2. 竞品 UIAutoDev 验证了技术路线但不可直接采用：License 弹窗、无面向 Agent 的语义压缩、服务端安全策略宽松。
3. 量化目标：Agent 单轮视图感知 ≤ 1200 token、元素定位正确率 ≥ 95%、抓取 P90 ≤ 2s、替代竞品迁移率 ≥ 80%（V1.0 后）。设计必须服务于这些数字：**可信、可控、可验证**。

### 包含什么功能板块

| 板块 | 内容 | 版本 |
|---|---|---|
| 主导航 | 侧栏一级导航：主页 / 设备 / 应用 / 命令 / 日志 / 设置；工作台内折叠为图标态 | V0.1 |
| 设备管理（默认落地页） | 平台分区设备列表、手动刷新与 5s 轮询、接入诊断、序列号复制 | V0.1 |
| 群控页 | 左栏勾选设备、右栏多设备网格同屏、降 fps / 分辨率 | V0.1 |
| 设备工作台 | scrcpy 实时投屏、鼠标键盘操控、竖排控制栏、坐标显示、设备信息条 | V0.1 |
| 常用面板 | 前台应用识别、应用启停与列表 | V0.1 |
| 元素查看 | 层级树、属性面板、画面-树双向联动、XPath 查询与反查、选择器生成、快照导入导出 | V0.1 / V0.2 |
| 布局智能 | 语义摘要（token 估算 + 压缩比）、异常诊断（6 类规则 + 画面标注）、快照存档与 diff | V0.1 / V0.2 |
| MCP 服务 | 每设备 SSE 端点、配置片段与一键接入、工具列表、只读模式 | V0.1 |
| 插件系统 | 插件卡片 / Tab 嵌入、`$u` 运行时 | V0.1 |
| 日志与设置 | 抓取 / MCP / 写操作审计记录，主题、驱动、轮询、存档、监听与安全 | V0.1 |

### 希望用户感受到什么

| 感受 | 设计落点 |
|---|---|
| **掌控** | 画面点哪查哪、树与属性随动、坐标精确到像素；一切操作有即时反馈 |
| **信任** | 每个结论带证据：诊断有量化数据、选择器标注命中数、摘要标注 token 数 |
| **专业克制** | 无 License 弹窗、无注册窗、无广告；界面安静、密度高但不拥挤 |
| **流畅** | 本机直连的即时感：抓取 ≤ 2s、投屏不掉帧、切换设备不打断 |
| **品质** | Apple 级细节：排版、材质、圆角、动效处处讲究，摸得到「原生感」 |

---

## 二、设计语言总则

1. **内容优先，工具退后。** 设备画面与 UI 树是绝对主角，界面只是承载它们的容器。所有装饰都服务于「读画面、读树、读诊断结论」。
2. **Apple 质感，工具克制。** 排版、留白、材质、动效学 Apple：区块之间用留白而非分割线分层，浮层与侧栏用毛玻璃材质，动效平滑短促。拒绝营销化表达。
3. **中性色阶 + 单一品牌蓝。** 层次由中性灰阶与透明度构建；唯一强调色为 Apple 蓝（`#0071e3` / `#0a84ff`），用于选中、聚焦、主按钮与链接；语义色只出现在状态、诊断与平台标识上。
4. **深浅双主题跟随系统。** `light` / `dark` / `system` 三态，token 全部走 CSS 变量重载，主题切换不闪烁；桌面壳材质与窗口背景随 `NSAppearance` 联动。
5. **密度分层。** 管理页（设备列表、设置、日志）是稀疏区：大留白、卡片式；工作台（树、属性、摘要）是密集区：13px 字号、28px 树行高、紧凑但可读。
6. **确定性可视化。** 状态灯、布尔属性语义色、诊断量化证据、选择器命中数、摘要 token 估算，数字与状态直接可见。
7. **键盘优先、鼠标可及。** XPath 输入回车即查、树支持上下键导航、Esc 关闭浮层、`Cmd+1..6` 切换导航；同时每个控件都可点击。
8. **动效服务状态。** 动画只出现在状态变化处，不做装饰性循环动画，尊重 `prefers-reduced-motion`。
9. **导航常驻、上下文不丢。** 侧栏在所有页面常驻（工作台折叠为图标态），当前所在域始终高亮；二级页面（群控、工作台）通过页内返回箭头回退，不依赖浏览器式历史。

### 2.1 核心关键词

专业、克制、精确、可扫描、内容优先、状态透明、macOS 原生感。

### 2.2 六条视觉原则

1. 内容优先：设备画面、元素树和诊断证据是主角，界面容器保持低对比。
2. 中性色分层：背景、侧栏、面板、卡片主要依靠中性色阶和 1px 描边区分。
3. 单一品牌色：Apple 蓝只用于链接、选中、焦点与当前上下文，不与成功色混用。
4. 语义色专用：绿色只表示成功或在线，黄色只表示警告，红色只表示错误和危险操作。
5. 密度可控：默认紧凑桌面密度；表格、属性和树承载大量信息，但保留清晰行高。
6. 状态完整：每个异步组件至少覆盖默认、悬停、聚焦、加载、禁用、成功、空、错误八类状态中的适用项。

### 2.3 新版原型带来的规范变更

| 维度 | v0.1 规范 | v0.2（新版原型） |
|---|---|---|
| 全局导航 | 无侧栏，顶部工具栏 + 页面返回 | 常驻左侧导航侧栏，6 个一级项；工作台折叠为 96px 图标态 |
| 底部状态栏 | 有（版本 / 内核状态灯 / 只读标识） | 取消，状态信息移入侧栏底部常驻区 |
| 控制栏位置 | 画面右侧独立一列 | 并入侧栏图标列，与导航项用分隔线隔开 |
| 面板 Tab 顺序 | 常用 / 元素查看 / 布局智能 / 插件 / MCP | 常用 / 插件 / 元素查看 / MCP（布局智能追加末位） |
| 面板 Tab 形态 | 下划线式 Tab（高 40） | 分段控件（pill 容器 + 激活白底卡片 + 底部 2px 指示线，高 48） |
| 设备表格列序 | 状态灯 / 平台 / 型号 / 产品 / 序列号 / 状态 / 操作 | # / 平台 / 序列号 / 型号 / 产品 / 状态 / 操作 |
| 首页主操作 | 刷新为 brand 主按钮 | 刷新与群控均为 outline 次按钮，主按钮留给行内「控制」 |
| 群控入口 | 直接进网格 | 先在左栏勾选设备，右栏出画面，未选时为空状态 |
| 设备画面 | 纯 letterbox 画布 | 画布 + 深色设备外框（模拟真机边框，radius 24 + 阴影） |
| 层级树 | 中性色树结构 | XML 语法着色树（新增语法高亮 token 组，见 3.1.9） |

---

## 三、Token 体系

> 对齐策略：语义结构、圆角与间距栅格沿用 ZCode 规范（标注「沿用」处详见 zcode-client-design-spec.md 第 3 章）；色彩取 Apple 的质感值（文字色 `#1d1d1f`、品牌蓝 `#0071e3`）。差异汇总见附录 A。

### 3.1 色彩

#### 3.1.1 背景层级

层次从低到高：`background` → `background-alt` → `canvas`（设备画面画布）→ `panel/header` → `card/input/menu/popover/toast` → `tag`。

| Token | Light | Dark | 用途 |
|---|---|---|---|
| `background` | `#fafafa` | `#171717` | 窗口底色、内容区 |
| `background-alt` | `#f5f5f5` | `#0d0d0d` | 区块交替底色、表格合计行、分段控件容器底 |
| `canvas` | `#f7f7f7`（浅，衬托深色设备框） | `#0a0a0a` | 设备画面画布（letterbox） |
| `surface` | `#0d0d0d` @4% | `#ffffff` @6% | 图标容器、弱衬底、代码块底 |
| `hover` | `#0d0d0d` @5% | `#ffffff` @10% | 列表行 / 按钮 / 导航项悬停 |
| `selected` | brand @12% | brand @22% | 选中态（树行、列表行） |
| `nav-selected` | brand @10%（`brand-soft`） | brand @22% | 侧栏当前导航项底 |
| `panel` / `header` | `#ffffff` | `#171717` | 面板、标题栏、工具栏 |
| `sidebar` | `#ffffff`（原生壳用 `.sidebar` 材质） | `#0a0a0a` | 主导航侧栏 |
| `card` / `input` / `menu` / `popover` / `toast` | `#ffffff` | `#262626` | 浮层与卡片 |
| `tag` / `secondary` | `#e6e6e6` | `#363636` | 标签底、次级按钮底 |
| `device-frame` | `#1d1d1f` | `#000000` | 设备画面外框（模拟真机边框） |

#### 3.1.2 文字层级

| Token | Light | Dark | 用途 |
|---|---|---|---|
| `foreground` | `#1d1d1f` | `#f5f5f7` | 正文 / 标题 |
| `foreground-subtle` | `#1d1d1f` @60% | `#f5f5f7` @60% | 次要说明、表头、属性名 |
| `foreground-subtlest` | `#1d1d1f` @40% | `#f5f5f7` @30% | 占位、弱提示、坐标角标 |
| `foreground-inverse` | `#ffffff` | `#0d0d0d` | 主按钮 / 彩色底上的反白文字 |
| 数字与坐标 | `font-variant-numeric: tabular-nums` | 同左 | bounds、尺寸、坐标、token 数一律等宽数字 |

#### 3.1.3 描边、品牌与语义色

| Token | Light | Dark | 用途 |
|---|---|---|---|
| `border` | `#0d0d0d` @10% | `#ffffff` @10% | 默认描边（hairline）、表格行分隔、卡片描边 |
| `border-hover` | `#0d0d0d` @15% | `#ffffff` @15% | 悬停描边 |
| `brand` | `#0071e3` | `#0a84ff` | **唯一强调色**：主按钮、链接、聚焦环、当前导航项、Tab 指示线、画面叠加层 |
| `brand-hover` | `#0077ed` | `#3b97ff` | 主按钮悬停 |
| `brand-active` | `#006edb` | `#0a6cdb` | 主按钮按下 |
| `brand-soft` | `#ebf4ff` | `#0d2a4a` | 品牌浅底：导航选中、高亮行、选中填充 |
| `success` | `#22c55e` | `#22c55e` | 成功、设备 connected、布尔 true |
| `warning` | `#ca8a04` | `#eab308` | 警告、booting/unhealthy、只读横幅 |
| `destructive` | `#ef4444` | `#f87171` | 危险操作（停止应用）、错误、unauthorized、布尔 false |
| `info` | `#64748b` | `#94a3b8` | 诊断 info 档、提示性标注、读类工具徽标 |
| `focus-ring` | `brand` | `brand` | 键盘焦点环 `ring-2` |

#### 3.1.4 状态灯

8px 圆点，颜色即语义：

| 状态 | Light | Dark | 说明 |
|---|---|---|---|
| connected | `#22c55e` | `#22c55e` | 常亮 |
| booting / unhealthy | `#ca8a04` | `#eab308` | 呼吸动画（1200ms 循环，透明度 100%↔40%） |
| unauthorized | `#ef4444` | `#f87171` | 常亮，行内附原因短语 |
| offline | `#1d1d1f` @25% | `#f5f5f7` @25% | 置灰 |

#### 3.1.5 画面叠加层（hierarchy overlay）

| Token | Light | Dark | 用途 |
|---|---|---|---|
| `overlay-stroke` | brand @45% | brand @55% | 全部节点边框（1px 实线） |
| `overlay-hover` | brand @75% | brand @85% | 悬停节点描边 |
| `overlay-selected` | brand 实色 2px + brand @12% 填充 | brand 2px + @20% 填充 | 选中节点 |
| `overlay-xpath-hit` | brand 1.5px 虚线 + brand @10% 填充 | 同左（提亮） | XPath 命中节点，与选中态区分 |
| `overlay-diagnostic` | 按档位取 `destructive` / `warning` / `info`，1.5px + 对应色 @14% 填充 | 同左 | 诊断结果标注 |

#### 3.1.6 平台标识色

小徽标专用，不用于大面积：

| 平台 | Light | Dark |
|---|---|---|
| Android | `#3ddc84` | `#4ade80` |
| iOS | `#6e6e73` | `#98989d` |
| HarmonyOS | `#e8541e` | `#ff7a45` |

#### 3.1.7 布尔属性与终端

- 属性面板布尔值：`true` 用 `success`、`false` 用 `destructive`（对齐 PRD 展示验收 B.2.4，见原型 04）。
- 终端 ANSI 16 色与光标 / 选区色：沿用 ZCode 规范 3.1.7。

#### 3.1.8 树内徽标

| 徽标 | 色 |
|---|---|
| 可交互节点（clickable 等标志位） | `brand` 图标 |
| 含文本节点 | `foreground-subtle` 图标 |
| 容器节点 | `foreground-subtlest` 图标 |
| 不可见节点（`visible=false`） | 整行文字与图标降至 `foreground-subtlest` |

#### 3.1.9 语法高亮（新增，用于 XML 层级树与 JSON 配置）

原型 04 的层级树与原型 06 的配置代码块使用同一套高亮 token，风格贴近 Xcode / VS Code 浅色主题，饱和度压低以避免与品牌蓝、语义色抢注意力。

| Token | Light | Dark | 用途 |
|---|---|---|---|
| `syntax-punct` | `#1d1d1f` @45% | `#f5f5f7` @45% | 尖括号、花括号、冒号、斜杠 |
| `syntax-tag` | `#a02020` | `#f0837f` | XML 标签名（`android.widget.LinearLayout`） |
| `syntax-attr` | `#0451a5` | `#7cb7ff` | 属性名 / JSON key（`resource-id`、`mcpServers`） |
| `syntax-value` | `#a31515` | `#f2a08c` | 属性值 / JSON 字符串 |
| `syntax-number` | `#098658` | `#6fd3a1` | 数值 |
| `syntax-line-selected` | `brand-soft` 整行底 | brand @22% 整行底 | 树中当前选中节点行（原型 04） |

约束：语法高亮仅用于代码与层级文本，不得外溢到普通 UI 文案；`syntax-tag` 与 `destructive` 视觉接近，因此错误态一律靠图标与前缀文案区分，不靠色相区分。

### 3.2 字体与排版

- **字体栈沿用 ZCode 3.2.1**：无内置字体文件，macOS 下即 SF Pro（sans）/ SF Mono（mono），中文回退 PingFang SC。
- **字号阶梯沿用 ZCode 3.2.2（基准 14px）**，另加两档：

| Token | 计算 | 默认值 | 用途 |
|---|---|---|---|
| `text-ui-xs` | base − 4px | 10px | 角标、微标注 |
| `text-ui-sm` | base − 2px | 12px | 辅助信息、密集列表、XML 树 |
| `text-ui-caption` | base − 1px | 13px | 属性值、表头、副标题 |
| `text-ui-base` | base | 14px | **正文默认**、导航项、Tab 文字 |
| `text-ui-lg` | base + 2px | 16px | 面板 / 小节标题 |
| `text-ui-xl` | base + 4px | 18px | 区块标题 |
| `text-ui-2xl` | — | 20px | 弹窗标题、MCP 区块标题 |
| `text-ui-3xl` | — | 24px | 页面标题（「设备管理」） |
| `text-display` | — | 28px | 空状态标题 |

- 字重：正文 400，列表 / 表头 / 导航项 500，标题 600；标题 `letter-spacing: -0.01em ~ -0.02em`。
- 行高：正文 1.5，标题 1.3，树行与表格 1.4。
- 等宽场景（SF Mono）：序列号、层级树、属性名与值、XPath 输入、包名与 Activity、摘要正文、MCP 配置 JSON、工具名、坐标与尺寸数值。

### 3.3 圆角

| Token | 值 | 用途 |
|---|---|---|
| `radius-xs` | 2px | 极小标签 |
| `radius-sm` | 4px | 紧凑元素、复选框 |
| `radius-md` | 6px | 按钮、输入框 |
| `radius-lg` | 8px | 图标按钮、导航项、分段控件内的激活项、代码块 |
| `radius-xl` | 12px | 卡片、弹窗、表格容器、面板分组 |
| `rounded-2xl` | 16px | 空状态虚线容器、群控格子 |
| `rounded-3xl` | 24px | 设备画面外框、插件图标容器 |
| `rounded-full` | 999px | 标签胶囊、状态徽标、分段控件容器 |

- 控件圆角必须落在 6–8px（对齐 PRD B.2.1），卡片 12px；不得混用 10px、14px 等中间值。
- 桌面壳原生部分（窗口、菜单）使用 macOS 连续圆角与系统默认值，不做自定义。

### 3.4 间距与尺寸

- **4pt 栅格沿用 ZCode 3.4**：`gap-1`=4 … `gap-8`=32。
- 骨架尺寸（按新版原型测量，向 4pt 取整，允许 ±2px）：

| 区域 | 尺寸 |
|---|---|
| 窗口 | 原型基准 1480×1060，最小 1280×800 |
| 标题栏 | 高 80px；左内边距 96px（避让交通灯）；右侧图标按钮 36×36，间距 8px |
| 侧栏展开态 | 宽 210px；项高 56px；左右内边距 12px；图标 22px，图标与文字间距 12px |
| 侧栏图标态 | 宽 96px；项高 56px；图标居中 22px |
| 侧栏分隔线 | 导航组与控制栏组之间 1px `border`，上下留白 12px |
| 内容区内边距 | 左右 48px，上 32px（管理类页面）；工作台面板内边距 24px |
| 页面标题区 | 标题 24px + 副标题 13px，间距 8px；标题区到工具栏 24px |
| 表格 | 表头行高 56px，数据行高 56px，合计行高 48px；单元格左右内边距 16px |
| 分段控件（面板 Tab） | 容器高 48px，`rounded-full`，内边距 4px；项高 40px，最小宽 112px |
| 群控左栏 | 宽 320px；复选项行高 48px |
| 设备画面区 | 默认宽 600px，可拖拽范围 360–900px；设备外框内边距 8px，圆角 24px |
| 设备信息条 | 高 64px，元素间距 16px |
| 元素查看双栏 | 属性栏 320px + 树栏自适应（最小 420px），中间 1px 分隔线 |
| 属性表 | 行高 48px，键列宽 140px |
| XML 树 | **行高 28px**，缩进 16px/级，字号 12px mono |
| 卡片 | 内边距 24px，卡片之间 16px |
| 弹窗 | 宽上限 480px，内边距 24px |

- 图标尺寸：行内 14、常规 16、导航与控制栏 22（36×36 触达区）、空状态插图 48、插件图标 64。
- 全部按钮触达区 ≥ 36×36px；投屏画面上节点热区 < 44dp 属于诊断告警（PRD 4.4）。

### 3.5 图标

- **lucide 线性图标沿用 ZCode 3.5**（1.5–2px 描边、圆头端点）。
- 图标携带语义色或 `foreground-subtle`，不使用多色图标；状态灯为 8px 实心圆点（非图标）。
- 加载中：`animate-spin` 旋转同一线性图标（刷新、抓取、重连）。
- 导航与控制栏图标映射：home / smartphone / layers / terminal / clipboard / gear（导航）；arrow-left / clock / menu / power / volume-2 / volume-1 / smartphone / bug / search / puzzle / video（控制栏，语义见交互原型 5.3）。

### 3.6 阴影与材质

| 场景 | Light | Dark |
|---|---|---|
| 浅浮层（菜单 / 气泡 / Tooltip / Toast） | `0 2px 10px rgba(15,23,42,.08), 0 1px 2px rgba(15,23,42,.05)` | `0 1px 2px rgba(2,6,23,.6)` |
| 深浮层（弹窗） | `0 16px 40px rgba(15,23,42,.12), 0 4px 12px rgba(15,23,42,.06)` | `0 16px 40px rgba(0,0,0,.5), 0 2px 8px rgba(0,0,0,.4)` |
| 设备画面外框 | `0 12px 32px rgba(15,23,42,.14)` | `0 12px 32px rgba(0,0,0,.55)` |

- 列表与卡片之间用描边与留白分层，不用阴影。
- 材质：原生壳标题栏与侧栏使用 `NSVisualEffectView`（`.headerView` / `.sidebar`，blending `.behindWindow`）；Web 端对应区域用 `backdrop-filter: blur(24px) saturate(180%)` + 半透明底（Light `rgba(255,255,255,.72)`，Dark `rgba(10,10,10,.70)`）。不支持 backdrop-filter 时回退实色。

### 3.7 动效

| Token | 值 | 用途 |
|---|---|---|
| `duration-fast` | 120ms | 悬停变色 |
| `duration-base` | 200ms | 叠加层淡入、Tab 切换、选中高亮、侧栏宽度折叠 |
| `duration-slow` | 300ms | 弹窗进出、诊断标注连线 |
| `ease-standard` | `cubic-bezier(0.3, 0.7, 0, 1)` | 全部位移动画的标准缓动 |

- 弹窗进场：透明度 0→1 + `scale(0.98→1)`，300ms；Toast 进场：淡入 + 上移 8px；侧栏折叠：宽度 210↔96 过渡 200ms，图标位置不跳动。
- 允许的动画仅：`transition-colors`、`transition-opacity`、轻量位移、`animate-spin`。无弹跳、无循环装饰动画。
- `prefers-reduced-motion: reduce` 时全部动画时长归零。

---

## 四、主题系统

| 主题 | 说明 |
|---|---|
| `light` / `dark` | 跟随用户设置或系统（`system`），基于本规范 token |
| 切换机制 | 根节点挂 `.dark` 或 `data-theme`，全部 token 以 CSS 变量重载；无硬编码色值 |
| 切换入口 | 标题栏主题图标按钮，`light → dark → system` 三态循环；图标随当前态变化 |
| 原生壳联动 | `NSAppearance` 随系统切换，材质与窗口背景自动适配；Web 内嵌页监听 `prefers-color-scheme` 同步 |
| 品牌蓝说明 | Light / Dark 使用不同档位（`#0071e3` / `#0a84ff`）保证对比度 ≥ WCAG AA（4.5:1） |

---

## 五、布局骨架

### 5.1 全局框架（原型 01）

```
┌──────────────────────────────────────────────────────────────┐
│ ○○○  LayoutSee                       [刷新] [主题] [设置]     │ 标题栏 80，材质
├────────────┬─────────────────────────────────────────────────┤
│ 主页       │                                                 │
│ 设备 ●     │            内容区（background）                  │
│ 应用       │                                                 │
│ 命令       │                                                 │
│ 日志       │                                                 │
│ 设置       │                                                 │
│ ─────────  │                                                 │
│ ● 服务正常  │                                                 │
└────────────┴─────────────────────────────────────────────────┘
    210
```

- 侧栏底色为 `sidebar`（原生壳用 `.sidebar` 材质），与内容区 `background` 之间 1px `border` 分隔。
- 无底部全局状态栏。内核状态灯与只读标识置于侧栏底部常驻区（图标态下仅保留 8px 圆点，Tooltip 说明）。
- 侧栏当前项：`nav-selected` 底 + `radius-lg` + `brand` 图标与文字，**不加左侧指示条**（原型 01 为整块圆角高亮）。

### 5.2 工作台骨架（原型 03–06）

```
┌────┬──────────────────────┬──────────────────────────────────┐
│ ⌂  │ ‹ Android model: … 序列号 [复制]                         │ 64
│ ── │──────────────────────┼──────────────────────────────────┤
│ ←  │                      │ [常用][插件][元素查看][MCP]        │ 48
│ 🕐 │   canvas + 设备外框   ├──────────────────────────────────┤
│ ☰  │   （等比居中）        │                                  │
│ ⏻  │                      │        右侧功能面板               │
│ 🔊 │                      │                                  │
│ …  │      600（可拖拽）    │           剩余宽度                │
└────┴──────────────────────┴──────────────────────────────────┘
  96
```

- 侧栏折叠为 96px 图标态：顶部为导航项（当前域「设备」以 `nav-selected` 高亮），分隔线以下为设备控制按钮组。
- 状态类控制按钮（审查元素、插件、冻结、只读）激活态为 `brand` 实底 + 反白图标；按键类为 ghost + `foreground-subtle`。
- 画面区与面板之间为 4px 命中宽度的可拖拽分隔线，悬停时显示 `brand` 细线。

---

## 六、页面规范

### 6.1 设备管理页（原型 01）

结构：页面标题区 → 工具栏 → 平台 Tab → 表格卡片 → 合计行。

- 标题「设备管理」24px semibold；副标题 13px `foreground-subtle`，随平台 Tab 变化。
- 工具栏：[刷新]、[群控] 均为 outline 次按钮，高 40px，图标 16 + 文字 14，间距 12px。
- 平台 Tab：下划线式 Tab（区别于面板内的分段控件），高 56px，项内 = 平台图标 16（平台色）+ 文字；激活项 `brand` 文字 + 底部 2px `brand` 线；容器底部 1px `border` 贯穿。
- 表格卡片：`radius-xl` + 1px `border`，无阴影；表头 13px medium `foreground-subtle`，行间 1px `border`；序列号列 mono；状态列 = 8px 状态灯 + 短语；操作列右对齐。
- 「控制」按钮：outline + `brand` 文字 + 鼠标图标，高 36，`radius-md`；不可用时降为 50% 透明度并 Tooltip 说明原因。
- 合计行：`background-alt` 底，13px `foreground-subtle`。
- 空状态：虚线边框卡片（`rounded-2xl`）+ 图标 48 + 标题 17 semibold + 三步指引 + [重新检测]。

### 6.2 群控页（原型 02）

- 左栏 320px：返回按钮为 36×36 方形 ghost（`surface` 底 + `radius-lg`）+ 标题 18px semibold；「全选 (N)」行下 1px 分隔线；设备复选项 = 16px 复选框 + mono 设备 id，行高 48，悬停 `hover`。
- 右栏：未选设备时虚线卡片空状态（图标 48 + 「未选择设备」17 semibold + 说明 13 subtle），卡片尺寸约占内容区 40% 宽、居中。
- 已选设备网格：2–3 列自适应，格子 `rounded-2xl` + 设备阴影，间距 16px；格子底部悬浮条 = 设备名 + 状态灯 + [控制]，`panel` 底 + 上侧 1px `border`。

### 6.3 设备工作台公共部分（原型 03）

- **设备信息条**：高 64px，`panel` 底 + 底部 1px `border`；返回箭头 36×36 ghost；`Android`（平台色徽标）+ `model: xxx` `product: xxx`（13px `foreground-subtle` 标签 + `foreground` 值）+ 序列号 mono + 复制图标 16。
- **画面区**：`canvas` 底 letterbox；设备外框 `device-frame` 色、`rounded-3xl`、内边距 8px、外加设备阴影；画面等比缩放居中，最大化利用可用高度。
- **画面角标**：右上角胶囊标识（`审查中` 用 `brand`、`已冻结` 用 `brand`、`只读` 用 `warning`），`rounded-full` + 12px 文字；左下角坐标提示为 mono 12px `foreground-subtlest`，`surface` 底胶囊。
- **重连遮罩**：画面覆盖 `background` @60% + spinner + 13px 文案 + [重试] 次按钮。

### 6.4 Tab 常用（原型 03）

- 分段控件在面板顶部居左，宽度按项数自适应，容器 `background-alt` + `rounded-full`；激活项 `panel` 底 + `radius-lg` + 浅浮层阴影 + `brand` 文字 + 底部 2px `brand` 指示线。
- 「获取当前 App」卡片：`radius-xl` + `border`，标题 16px semibold；字段标签 13px `foreground-subtle` + 输入框（高 40，mono，`radius-md`）；字段之间 16px。
- 按钮行：[刷新] 为 `brand` 主按钮、[停止] 为 `destructive` 主按钮、[启动] 为 outline 次按钮，高 40，间距 12px。危险按钮点击后必须二次确认弹窗。
- 已安装应用列表区块（规范补充）：搜索输入框 + 虚拟滚动列表，行高 40，包名 mono 13 + 应用名 13 `foreground-subtle`，行内操作在悬停时出现。

### 6.5 Tab 插件（原型 05）

- 区块标题 16px semibold + 副标题 13px `foreground-subtle`，与内容间距 24px。
- 空状态：虚线卡片（`rounded-2xl`，虚线 1px `border`）居中，拼图图标 48 `foreground-subtlest` + 标题 17 semibold + 说明 13 subtle + [浏览插件] `brand` 主按钮；卡片高约 340px。
- 插件卡片：`radius-xl` + `border`，悬停 `hover` 底 + `border-hover`；卡片头 = 图标 32 + 名称 14 medium + 版本 12 `foreground-subtlest`，右上「⋯」ghost 图标按钮。
- 失败态：卡片内联错误（`destructive` 图标 + 文案 + [重新加载] [查看日志]），不影响其他卡片与主界面。

### 6.6 Tab 元素查看（原型 04）

- **XPath 输入行**：输入框占据剩余宽度（高 44，mono 13，`radius-lg`），右侧 [查询] outline 按钮（放大镜图标 + 文字），间距 12px；语法错误时输入框描边转 `destructive` 并在下方 12px 处内联报错。
- **操作行**：[刷新 UI] [重置] outline 次按钮（高 36，图标 + 文字）；右侧 `Tag: xxx` `Size: 1154×376` 为 13px，标签用 `foreground-subtle`、值用 mono `foreground`，`tabular-nums`。
- **属性表**：无外框，行间 1px `border`；键列 13px `foreground-subtle`，值列 13px mono；布尔值 true `success` / false `destructive`；行悬停 `hover`，右侧出现复制图标。
- **XML 树**：mono 12px，行高 28，缩进 16px/级；语法着色按 3.1.9；折叠三角 12px `foreground-subtlest`；选中行 `syntax-line-selected` 整行底；不可见节点整行降至 `foreground-subtlest`；虚拟滚动（> 2000 节点）。
- **画面叠加层**：按 3.1.5，默认全节点淡蓝描边、选中实线加粗、XPath 命中虚线；叠加层与画面之间不加额外遮罩，保证画面可读。

### 6.7 Tab MCP（原型 06）

- 区块标题「MCP Server」20px semibold + 副标题 13px `foreground-subtle`。
- 客户端分段控件：`background-alt` + `rounded-full` 容器，项内 = 图标 14 + 文字 13；激活项 `panel` 底 + 1px `brand` 描边 + `brand` 文字（原型 06 为描边式激活，与面板 Tab 的下划线式区分）。
- 「配置」卡片：`radius-xl` + `border`；卡片头 = 标题 14 medium + 右上复制图标按钮；代码块 `surface` 底 + `radius-lg` + mono 13 + 语法高亮（3.1.9）+ 内边距 16。
- 「可用工具」卡片：卡片头右侧为计数徽标（13px `foreground-subtle`，如「9 个」）；列表行高 40，工具名 mono 13 `foreground`，说明 13 `foreground-subtle` 左对齐于第二列（列宽比约 4:6）；行间 1px `border`，悬停 `hover`。
- 只读模式提示：`warning` 细横幅置于卡片区顶部，含开关与说明文案。

### 6.8 Tab 布局智能（原型未出图，规范定义）

- 三个纵向卡片：语义摘要 → 异常诊断 → 快照存档与 diff（V0.2 置灰）。
- 摘要卡片头：token 估算与压缩比用 mono `tabular-nums` 展示（如 `1,180 token · 压缩比 12.4×`），右上 [复制] [裁剪策略] ghost 按钮；正文 mono 13，可折叠层级，超长区域内滚动。
- 诊断结果项：左侧 severity 图标（error `destructive` / warning `warning` / info `info`）+ 类型 14 medium + 涉及节点 mono 12 + 量化证据 13 `foreground-subtle` + 建议 13；整项可点，选中时 `selected` 底并在画面标注。
- 通过态：`success` 图标 + 「未发现布局异常（已检查 6 类规则，N 个节点）」。

### 6.9 日志页与设置页（原型未出图，规范定义）

- **日志页**：过滤条（分段控件 + 时间范围 + 搜索框）→ 表格卡片（时间 mono / 类型徽标 / 来源徽标 ui·mcp·plugin / 对象 mono / 结果语义色 / 耗时 mono）→ 详情抽屉（右侧滑入 480px，`popover` 底 + 深浮层阴影）。
- **设置页**：左侧分组导航（宽 200px，项高 40，选中 `nav-selected`）+ 右侧表单（单列，最大宽 640px）；分组之间 32px 间距；每项 = 标签 14 + 说明 13 `foreground-subtle` + 控件右对齐；高风险项（监听地址、清理存档）操作前弹确认弹窗并在说明中标红后果。

---

## 七、组件规范

| 组件 | 规范 |
|---|---|
| 主按钮 | `brand` 底 + 反白文字，`radius-md`，高 40（紧凑场景 32）；悬停 `brand-hover`、按下 `brand-active`；禁用 50% 透明度 |
| 次按钮（outline） | 透明底 + `border` + `foreground` 文字，悬停 `hover` + `border-hover`；首页刷新 / 群控、面板内 [刷新 UI] [重置] [查询] 均为此变体 |
| 危险按钮 | `destructive` 底 + 反白文字（应用「停止」），或 ghost + `text-destructive`；一律二次确认 |
| 图标按钮 | 36×36 ghost，`radius-lg`，悬停 `hover`；状态类激活为 `brand` 实底 + 反白图标 |
| 导航项 | 高 56，`radius-lg`，图标 22 + 文字 14 medium；选中 `nav-selected` + `brand` 内容；图标态下仅图标居中 + Tooltip |
| 分段控件 | 容器 `background-alt` + `rounded-full` + 4px 内边距；激活项 `panel` 底 + `radius-lg` + 浅浮层阴影 + `brand` 文字（面板 Tab 追加底部 2px 指示线，MCP 客户端切换用 1px `brand` 描边） |
| 下划线 Tab | 仅用于平台分区（Android / iOS / HarmonyOS），高 56，激活 `brand` 文字 + 底部 2px `brand` 线 |
| 输入框 | `input` 底 + `border`，高 40，`radius-md`；悬停 `border-hover`，聚焦 `ring-2 focus-ring`；mono 类输入（XPath、包名、序列号）用等宽字体 |
| 复选框 | 16×16，`radius-sm`；选中 `brand` 底 + 反白勾；半选态为 `brand` 底 + 横线（群控全选） |
| 表格 | 容器 `radius-xl` + `border`；表头 13 medium `foreground-subtle`；行高 56；行间 1px `border`；悬停 `hover`；合计行 `background-alt` |
| 属性表 | 键列 140px `foreground-subtle`，值列 mono；行高 48，行间 1px `border`；布尔值语义色 |
| 层级树 | mono 12，行高 28，缩进 16；语法高亮 3.1.9；选中整行底 `brand-soft`；虚拟滚动 |
| 代码块 | `surface` 底 + `radius-lg` + mono 13 + 内边距 16 + 右上复制按钮；JSON / XML 语法高亮 |
| 标签与徽标 | `tag` 底 + `rounded-full` + `text-ui-xs/sm`；平台徽标用平台色，状态徽标用状态色，MCP 读/写徽标用 `info` / `brand` |
| 状态灯 | 8px 实心圆点 + 文字短语；异常态呼吸动画 |
| Tooltip | 深色底反白（Light `#2b2b2b` / Dark `#f5f5f7` 反色文字），`radius-lg`，延迟 300ms；图标态导航与控制栏按钮必备 |
| Toast | `card` 底 + 浅浮层阴影 + `radius-xl` + 语义色前缀图标；窗口右上，5s 自动消失 |
| 弹窗 | 宽上限 480px，`radius-xl` + 深浮层阴影；标题 20 semibold，正文 14；底部操作右对齐 [次][主]；破坏性弹窗在标题区说明后果 |
| 空状态 | 虚线边框卡片（`rounded-2xl`）+ 图标 48 + 标题 17 semibold + 说明 13 subtle + 引导按钮（主按钮） |
| 状态横幅 | 细条式（error / warning / info 语义底 + 同色文字 + 前缀图标），横贯面板或内容区顶部，可关闭；只读与离线回看模式常驻不可关闭 |
| 设备画面框 | `device-frame` 底 + `rounded-3xl` + 8px 内边距 + 设备阴影；内部画面等比缩放 |
| 骨架屏 | `surface` 底占位块 + 1200ms 呼吸；用于设备列表与应用列表首次加载 |

---

## 八、交互原则

在 ZCode 规范第 6 章（内容可视化、权限安全、高效可恢复、容错引导）基础上补充：

1. **三方联动即时报**：画面-树-属性任意一侧的选择，其余两侧同步响应（树定位 ≤ 200ms，验收 B.3.5）。
2. **抓取原子性外显**：冻结 → dump → 截图是一步不可分操作；未冻结成功时顶部黄条标注「截图与层级可能不同步」。
3. **模式差异必须明示**：叠加层开启后画面单击语义从「操作设备」变为「选择节点」，必须通过画面角标 + 控制栏按钮激活态双重提示。
4. **状态永远显式**：冻结角标、只读横幅、离线浮层、重连遮罩、内核状态灯，绝不静默。
5. **结论必须带证据**：诊断项带量化数据、选择器带命中数、摘要带 token 数。
6. **写操作可感知、可撤销**：注入有即时画面反馈；只读模式是全局门禁；破坏性命令二次确认；全部写操作可审计。
7. **键盘路径完备**：`Cmd+1..6` 导航、XPath 回车查询、树上下键移动、Enter 展开、Esc 逐级退出、`Cmd+C` 复制上下文标识。
8. **空状态即引导**：无设备、无层级、无插件、无诊断结果、未选设备，各自给出下一步动作。
9. **错误内联 + 下一步**：错误显示在发生的位置，并附可执行建议（重试 / 切换驱动 / 打开设置 / 查看日志）。
10. **无死入口**：未落地的导航项一律置灰 + Tooltip 说明版本，禁止点击无响应。
11. **深浅主题零感知切换**：跟随系统即时切换、无闪烁、无残留反色区域。

---

## 九、技术落地

### 9.1 Web（`repos/web`，UI 唯一实现）

```css
:root {
  /* 背景层级 */
  --bg: #fafafa; --bg-alt: #f5f5f5; --canvas: #f7f7f7;
  --panel: #ffffff; --card: #ffffff; --tag: #e6e6e6; --sidebar: #ffffff;
  --surface: rgba(13,13,13,.04); --hover: rgba(13,13,13,.05);
  --selected: rgba(0,113,227,.12); --nav-selected: rgba(0,113,227,.10);
  --device-frame: #1d1d1f;
  /* 文字 */
  --fg: #1d1d1f; --fg-subtle: rgba(29,29,31,.6); --fg-subtlest: rgba(29,29,31,.4);
  /* 描边与强调 */
  --border: rgba(13,13,13,.10); --border-hover: rgba(13,13,13,.15);
  --brand: #0071e3; --brand-hover: #0077ed; --brand-active: #006edb; --brand-soft: #ebf4ff;
  /* 语义 */
  --success: #22c55e; --warning: #ca8a04; --destructive: #ef4444; --info: #64748b;
  /* 叠加层 */
  --overlay-stroke: rgba(0,113,227,.45); --overlay-selected: rgba(0,113,227,.12);
  /* 语法高亮 */
  --syntax-punct: rgba(29,29,31,.45); --syntax-tag: #a02020; --syntax-attr: #0451a5;
  --syntax-value: #a31515; --syntax-number: #098658;
  /* 骨架尺寸 */
  --titlebar-h: 80px; --sidebar-w: 210px; --sidebar-w-collapsed: 96px;
  --devicebar-h: 64px; --segment-h: 48px; --tree-row-h: 28px;
  /* 字体 */
  --font-sans: ui-sans-serif, system-ui, -apple-system, "SF Pro Text", "PingFang SC", sans-serif;
  --font-mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, "PingFang SC", monospace;
}
.dark {
  --bg: #171717; --bg-alt: #0d0d0d; --canvas: #0a0a0a;
  --panel: #171717; --card: #262626; --tag: #363636; --sidebar: #0a0a0a;
  --surface: rgba(255,255,255,.06); --hover: rgba(255,255,255,.10);
  --selected: rgba(10,132,255,.22); --nav-selected: rgba(10,132,255,.22);
  --device-frame: #000000;
  --fg: #f5f5f7; --fg-subtle: rgba(245,245,247,.6); --fg-subtlest: rgba(245,245,247,.3);
  --border: rgba(255,255,255,.10); --border-hover: rgba(255,255,255,.15);
  --brand: #0a84ff; --brand-hover: #3b97ff; --brand-active: #0a6cdb; --brand-soft: #0d2a4a;
  --warning: #eab308; --destructive: #f87171; --info: #94a3b8;
  --overlay-stroke: rgba(10,132,255,.55); --overlay-selected: rgba(10,132,255,.20);
  --syntax-punct: rgba(245,245,247,.45); --syntax-tag: #f0837f; --syntax-attr: #7cb7ff;
  --syntax-value: #f2a08c; --syntax-number: #6fd3a1;
}
```

### 9.2 macOS 原生壳（`repos/mac`）

| 项 | 实现 |
|---|---|
| 材质 | `NSVisualEffectView`：标题栏 `.headerView`、侧栏 `.sidebar`（内容区为实色，不加材质以保证画面与树的可读性） |
| 强调色 | 窗口 `accentColor` = `#0071e3`（Light）/ `#0a84ff`（Dark），随外观自动切换 |
| 字体 | 系统字体（SF Pro），中文自动回退 PingFang SC；字号 pt = px |
| 主题联动 | `NSAppearance` 跟随系统；通知内嵌 Web 层同步 `.dark` |
| 窗口 | 最小尺寸 1280×800；交通灯左内边距对应标题栏 96px 让位区 |

---

## 十、对齐检查清单（自测）

- [ ] 深 / 浅两套完整 token，跟随系统切换不闪烁，无残留反色区域
- [ ] 唯一强调色为 Apple 蓝；语义色仅用于状态；平台徽标仅用平台色；语法高亮不外溢到普通文案
- [ ] 侧栏两态齐备：展开 210 / 图标 96，折叠动画 200ms，当前项 `nav-selected` 圆角高亮且无左指示条
- [ ] 无底部全局状态栏；内核状态灯与只读标识在侧栏底部常驻
- [ ] 未落地导航项（主页 / 应用 / 命令，V0.1）置灰 + Tooltip 版本说明，无死入口
- [ ] 面板 Tab 顺序为 常用 → 插件 → 元素查看 → MCP（→ 布局智能），形态为分段控件
- [ ] 设备表格列序为 # / 平台 / 序列号 / 型号 / 产品 / 状态 / 操作，序列号与数值 mono + tabular-nums
- [ ] 控件圆角 ∈ {6, 8}，卡片 12，空态与格子 16，设备外框 24，胶囊仅用于标签与分段容器；间距全部落在 4pt 栅格
- [ ] 设备画面带 `device-frame` 外框与阴影，角标齐备（审查中 / 已冻结 / 只读），左下角坐标 mono
- [ ] 画面叠加层遵循 3.1.5：默认淡蓝描边、选中实线加粗、XPath 命中虚线、诊断用语义色
- [ ] 树行高 28、缩进 16、选中整行 `brand-soft`；属性布尔 true 绿 / false 红
- [ ] 主按钮 brand；应用「停止」用 destructive 且二次确认；只读模式下写类控件统一置灰加锁
- [ ] 空状态虚线卡片 + 引导按钮（未选设备 / 无设备 / 无插件 / 无层级 / 无诊断结果全覆盖）
- [ ] 错误内联「问题 + 可执行下一步」，技术细节折叠，不出现裸堆栈
- [ ] 加载统一 spinner 与骨架屏；重连遮罩、离线浮层、只读横幅全部就位
- [ ] 动效仅 transition-colors / opacity / 轻位移 / spinner，尊重 prefers-reduced-motion
- [ ] 全部文案走 i18n（至少中英双语）；文件 / 行号 / URL 渲染为可点击链接
- [ ] 桌面壳原生部分使用系统材质与连续圆角，无自定义异形窗口

---

## 附录 A：与 ZCode 规范的差异对照

| 维度 | ZCode 基准 | LayoutSee 采用 | 理由 |
|---|---|---|---|
| 正文文字色 | `#262626` / `#e5e5e5` | `#1d1d1f` / `#f5f5f7` | Apple 文字色，对比度更佳 |
| 品牌色 | sky-500 `#0ea5e9` | Apple 蓝 `#0071e3` / `#0a84ff` | 设计风格参考为 apple.com |
| 选中态 | 中性 `#0d0d0d` @5% / `#fff` @10% | brand @12% / @22%，导航项 @10% / @22% | Apple 选中带品牌色调，树与导航中更醒目 |
| 主按钮 | 近黑底（Light）/ 近白底（Dark） | brand 蓝底反白 | Apple 主按钮语义，全主题一致 |
| 材质 | 无 | 原生壳标题栏与侧栏毛玻璃（Web 用 backdrop-filter 回退） | Apple 质感核心 |
| 新增 token | — | `canvas`、`nav-selected`、`device-frame`、状态灯、叠加层、平台色、语法高亮组、骨架尺寸组、`info`、`brand-hover/active/soft`、动效时长 | LayoutSee 特有场景（投屏画布、层级叠加、诊断、侧栏导航） |
| 其余（圆角 / 间距 / 图标 / 阴影 / 动效原则 / 字体栈） | 沿用 | 完全一致 | 见第三章各节 |

> PRD 3.9 与 B.2.1 要求「视觉规范对齐 zcode-client-design-spec.md」，本附录的调整全部落在色彩值与新增 token 层面，语义结构（token 名、层级、栅格、圆角、动效原则）与 ZCode 保持一致，满足对齐验收要求。

## 附录 B：v0.1 → v0.2 变更记录

1. 视觉依据从 `assets/pic/`（竞品截图）切换为 `docs/designs/redesign/`（新版原型），第二章「对竞品截图的取舍」替换为 2.3「新版原型带来的规范变更」。
2. 新增第五章「布局骨架」，定义全局框架与工作台骨架、侧栏两态、控制栏并入侧栏的处理。
3. 第六章按新版原型逐页重写；新增群控页两栏结构、设备信息条、分段控件、日志页与设置页规范。
4. 新增 token：`nav-selected`、`device-frame`、语法高亮组（3.1.9）、骨架尺寸组（3.4）；`canvas` 浅色档由 `#e5e5e5` 调整为 `#f7f7f7` 以衬托深色设备外框。
5. 移除底部全局状态栏相关规范，状态信息改挂侧栏底部。
6. 组件章节新增：导航项、分段控件、复选框、属性表、层级树、设备画面框、骨架屏；明确下划线 Tab 仅用于平台分区。
7. 交互原则新增第 3、10 条（模式差异明示、无死入口），检查清单同步扩充。
8. 原型未覆盖但 PRD 要求的部分（布局智能 Tab、冻结与只读按钮、日志页、设置页）在文中显式标注「规范定义 / 规范补充」，待确认项见 [交互原型文档第 9 章](./interaction-prototype.md#9-与-prd-及旧版设计的差异与待确认项)。










