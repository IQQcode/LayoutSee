# ZCode 客户端设计规范（Design Spec）

> 版本：ZCode 3.9.1（dev.zcode.app，Electron 桌面客户端）
> 本文档基于对 ZCode 3.9.1 客户端产物（app bundle 内 CSS 变量、组件类名、i18n 文案、进程结构）的逆向提取与实际使用观察整理，目的是为 **LayoutSee Mac 端**的视觉规范与交互设计提供对齐基准。
> 整理日期：2026-08-24

---

## 1. 产品概览与信息架构

ZCode 是智谱 AI 出品的 AI 编程 / Agent 桌面客户端，核心形态是 **「工作区（Workspace）+ 会话（Session）+ Agent 工具调用」** 的对话式开发环境。

### 1.1 核心界面结构

```
┌─────────────────────────────────────────────────────────────┐
│ 标题栏（原生窗口标题栏，支持系统深浅主题）                          │
├───────────────┬─────────────────────────────────────────────┤
│ 左侧栏         │  主面板                                        │
│ 工作区树       │  ┌─────────────────────────────────────────┐ │
│  · 文件节点     │  │ 会话消息流（Markdown 渲染，流式输出）        │ │
│  · 会话节点     │  │  · 用户消息 / Agent 回复 / 工具调用卡片       │ │
│  · 技能节点     │  │  · 代码块高亮 / 表格 / 公式 / 图片            │ │
│  · 插件节点     │  ├─────────────────────────────────────────┤ │
│  · 子代理节点    │  │ 输入区（多行输入、@文件引用、/命令、发送按钮）   │ │
│  · 命令节点     │  └─────────────────────────────────────────┘ │
├───────────────┴─────────────────────────────────────────────┤
│ 状态栏 / 面板切换 / 终端面板（可选）                                │
└─────────────────────────────────────────────────────────────┘
```

- **左侧栏**：工作区树，按节点类型着色区分（见 3.1.4 节点色），支持展开/折叠分组、悬停高亮。
- **主面板**：Markdown 优先的消息流 + 底部输入区；另含设置页、插件市场页（hero 图 + 示例 Prompt + 分类列表）、使用统计（图表 + 热力图）等二级页面。
- **浮层体系**：弹窗（Dialog）、下拉菜单（Menu）、气泡（Popover）、提示（Tooltip / Toast）、CUA 权限面板（独立窗口）。

### 1.2 能力结构（插件体系）

客户端扩展点分为五类：`MCP`、`Skill`、`Command`、`Agent`、`Hook`，由插件市场（Marketplace）统一管理安装/更新/卸载/启停，内置插件可恢复（restorable）。

---

## 2. 设计语言总则

1. **内容优先、界面退后**：界面是 Markdown 内容与工具执行状态的容器，视觉层级服务于"读代码、读过程、读结果"。
2. **中性色阶构建层次，单一强调色**：默认主题以中性灰阶 + 透明度构建界面层级，语义色只用于状态（成功/警告/错误）与类型标识。
3. **克制圆角、轻阴影、极简描边**：卡片 12px、控件 6–8px、胶囊 999px；层次靠"背景色阶差 + 1px 描边 + 悬停变色"，而非重阴影。
4. **深浅双主题跟随系统**：`light` / `dark` / `system` 三态，另有 `zai-light` / `zai-dark` 品牌主题（下文简称 zai 主题）。
5. **键盘优先、鼠标可及**：核心操作均有快捷键与键盘路径（Tab 补全、回车发送、Esc 关闭浮层），同时全部控件可点击。

---

## 3. 设计 Token 体系

> 说明：默认主题基于 Tailwind CSS v4 语义变量（`--color-*`，oklch 色彩空间 + `color-mix` 透明度混合）；zai 主题为品牌化主题，使用具体十六进制色值。下文"默认主题"给出语义值与对应实色，"zai 主题"给出实色值。LayoutSee 采用其中一套即可，推荐默认主题。

### 3.1 色彩系统

#### 3.1.1 背景层级（surface elevation）

层次从低到高：`background` → `background-alt` → `surface` → `panel/header/tab` → `card/input/menu/popover/toast/tooltip` → `menu-hover/tag`。

| Token | 默认主题 Light | 默认主题 Dark | zai-light | zai-dark | 用途 |
|---|---|---|---|---|---|
| `background` | neutral-50 `#fafafa` | neutral-900 `#171717` | `#f8f8f8` | `#161616` | 窗口底色 |
| `background-alt` | neutral-50 60% | neutral-900 60% | — | — | 次要底色 |
| `surface` | `#0d0d0d` @3% | `#ffffff` @5% | — | — | 图标容器、弱衬底 |
| `surface-hover` / `hover` | `#0d0d0d` @5% | `#ffffff` @10% | — | — | 列表项悬停 |
| `selected` | `#0d0d0d` @5% | `#ffffff` @10% | — | — | 选中态 |
| `panel` / `header` | `#fff` | neutral-900 `#171717` | `#fff` | `#202020` | 面板/头部 |
| `tab` / `tab-active` | neutral-800 `#262626` / neutral-950 `#0a0a0a` | 同左 | `#f0f0f0` / `#fff` | `#202020` / `#161616` | 标签页（选中向底色沉一级） |
| `card` / `input` / `menu` / `popover` / `toast` / `tooltip` | `#fff` | neutral-800 `#262626` | `#fff` | `#2b2b2b` | 浮层与卡片 |
| `menu-hover` / `tag` / `secondary` | neutral-700 `#404040` | neutral-700 | `#e6e6e6` | `#363636` | 菜单悬停、标签底 |
| `sidebar` | neutral-100 `#f5f5f5` | neutral-950 `#0a0a0a` | `#f0f0f0` | `#161616` | 左侧栏底色 |

> 注意：侧栏始终比主面板底色深一级（Light 下 `#f5f5f5`/`#f0f0f0` vs 背景 `#fafafa`/`#f8f8f8`，Dark 下 `#0a0a0a`/`#161616` vs `#171717`/`#161616`），形成稳定的横向分区感；zai 主题下侧栏与背景同色或略深。

#### 3.1.2 文字层级

| Token | 默认 Light | 默认 Dark | 用途 |
|---|---|---|---|
| `foreground` | neutral-800 `#262626` | neutral-200 `#e5e5e5` | 正文/标题 |
| `foreground-subtle` | neutral-800 @60% | neutral-200 @60% | 次要说明文字 |
| `foreground-subtlest` | neutral-800 @40% | neutral-200 @30% | 弱提示、占位 |
| `foreground-inverse` | `#fff` | `#000` | 主按钮/彩色底上的反白文字 |

#### 3.1.3 描边与语义色

| Token | Light | Dark | 用途 |
|---|---|---|---|
| `border` | `#0d0d0d` @10% | `#ffffff` @10% | 默认描边 |
| `border-hover`（`input-border-focused` 同源） | `#0d0d0d` @15% | `#ffffff` @15% | 悬停/聚焦描边 |
| `brand` | sky-500 `#0ea5e9` | sky-500 | 品牌强调、链接、聚焦环 |
| `primary`（按钮主色） | neutral-950 `#0a0a0a` | neutral-50 `#fafafa` | 主操作按钮 |
| `primary-foreground` | `#fff` | `#000` | 主按钮文字 |
| `destructive` | red-500 `#ef4444` | red-400 `#f87171` | 危险操作/错误（zai：`#e03131` / `#ff5c5c`） |
| `success` | green-500 `#22c55e` | green-500 | 成功状态 |
| `warning` | yellow-600 `#ca8a04` | yellow-500 `#eab308` | 警告状态（zai：`#e07b00` / `#ff8a30`） |
| `focus ring` | `input-border-focused`（= border-hover / brand） | 同左 | 键盘焦点环 `ring-2` |

#### 3.1.4 节点类型色（工作区树）

左侧树节点按类型用色：底 = 类型色 @16–18% 透明度，前景 = 类型色（Light 深一档 / Dark 亮一档），悬停 = @22–24%。

| 节点类型 | Light 前景 | Dark 前景 | 色调 |
|---|---|---|---|
| 文件 / 目录 | `#1a70b8` | `#8fc5ef` | sky |
| 会话 | `#14807a` | `#93d8d2` | teal |
| 技能（Skill） | `#7453b0` | `#bda5e6` | violet |
| 插件 | `#b87a1a` | `#efc58f` | amber |
| 子代理（Subagent） | `#6f7a2f` | `#b7bd75` | olive |
| 命令 | `#566270` | `#b5c0cc` | slate |

#### 3.1.5 Git / Diff 状态色

| 状态 | Light | Dark | 备注 |
|---|---|---|---|
| 新增 / added | `#1e8a3e` | `#46bf72` | 默认主题 teal-400 `#2dd4bf` |
| 修改 / modified | `#e07b00` | `#ff8a30` | |
| 删除 / deleted | `#e03131` | `#ff5c5c` | |
| 重命名 / renamed | `#0b7fff` | `#4099ff` | |

#### 3.1.6 交互状态色（Agent 特有）

| 场景 | Light | Dark |
|---|---|---|
| 询问（ask，如向用户提问） | 文字 `#06d`，底 `#ebf4ff` | 文字 `#80beff`，底 `#001d3d` |
| 确认（confirmation） | 文字 `#166b32`，底 `#eaf7ee` | 文字 `#87d9a4`，底 green @29% |
| 上下文拆解（context breakdown） | sky 阶梯 `#0b7fff → #338fff → #5ca7ff → #85bbff → #acd0ff → #c8ddff → #e0ecff` | 同色系提亮 |

#### 3.1.7 终端 ANSI 16 色

标准 xterm 语义色，Light 加深、Dark 提亮：

| 色 | Light | Dark | 色 | Light | Dark |
|---|---|---|---|---|---|
| black | `#5c5c5c` | `#363636` | bright-black | `#888` | `#747474` |
| red | `#e03131` | `#ff5c5c` | bright-red | `#f99` | `#e03131` |
| green | `#1e8a3e` | `#46bf72` | bright-green | `#87d9a4` | `#1e8a3e` |
| yellow | `#e07b00` | `#ff8a30` | bright-yellow | `#ffb26b` | `#e07b00` |
| blue | `#0b7fff` | `#4099ff` | bright-blue | `#80beff` | `#06d` |
| magenta | `#7b5ce5` | `#9e77ed` | bright-magenta | `#a888f2` | `#9e77ed` |
| cyan | `#0aa7a7` | `#42c8c8` | bright-cyan | `#8ee5e5` | `#0aa7a7` |
| white | `#adadad` | `#0d0d0d` | bright-white | `#f8f8f8` | `#0d0d0d` |

光标：`#f8f8f8`（Light）/ `#0d0d0d`（Dark），选区：sky @26–28%。

#### 3.1.8 品牌色（zai 主题）

| Token | Light | Dark |
|---|---|---|
| 主蓝 | `#0b7fff` | `#4099ff` |
| 亮蓝 | `#80beff` | `#80beff` |
| 深蓝字 | `#06d` | `#80beff` |
| 深藏青（accent 底） | `#ebf4ff` | `#001d3d` |
| 强调渐变文字 | `#0a0a0a`（strong）/ 38%（soft） | `#fff` / `#fff3` |

### 3.2 字体与排版

#### 3.2.1 字体栈

```css
--font-sans: ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji";
--font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
             "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", monospace;
```

- 无内置字体文件，纯系统字体栈：macOS 下即 **SF Pro（sans）/ SF Mono（mono）**，中文回退 **PingFang SC**。
- 标题字体（`font-heading`）为可配置 token，默认回退 sans 栈。
- LayoutSee 对齐：macOS 原生直接使用系统字体即可获得一致观感。

#### 3.2.2 字号阶梯（基于可配置基准 14px）

基准字号 `--ui-font-size: 14px`（用户可在约 12–20px 范围调整），其余档位以基准偏移计算：

| Token | 计算 | 默认值 | 用途 |
|---|---|---|---|
| `text-ui-xs` | base − 4px | 10px | 角标、微标注 |
| `text-ui-sm` | base − 2px | 12px | 辅助信息、密集列表 |
| `text-ui-caption` | base − 1px | 13px | 说明文字 |
| `text-ui-base` | base | 14px | **正文默认** |
| `text-ui-lg` | base + 2px | 16px | 小节标题 |
| `text-ui-xl` | base + 4px | 18px | 区块标题 |
| （页面级标题） | — | 24px | `text-2xl font-semibold tracking-tight`，如插件详情标题 |

- 标题字重 `font-semibold`（600），正文 400。
- Markdown 正文用 `prose` + `prose-sm`（tailwindcss-typography）排版：段落 14px、标题层级、表格边框、引用、`kbd` 阴影均内置。

### 3.3 圆角

| Token | 值 | 典型用途 |
|---|---|---|
| `radius-xs` | 2px | 极小标签 |
| `radius-sm` | 4px | 紧凑元素 |
| `radius-md` | 6px | 按钮、输入框 |
| `radius-lg` | 8px | 列表行、菜单项 |
| `radius-xl` | 12px | 卡片、弹窗、组容器 |
| `rounded-2xl` | 16px | 图标容器、插件图标 |
| `rounded-3xl` | 24px | Hero、示例 Prompt 胶囊 |
| `rounded-full` | 999px | 圆形图标按钮、标签胶囊 |

### 3.4 间距与尺寸

- 间距基于 4px 栅格：`gap-1`=4、`gap-1.5`=6、`gap-2`=8、`gap-2.5`=10、`gap-3`=12、`gap-4`=16、`gap-5`=20、`gap-6`=24、`gap-8`=32。
- 典型组合：列表行内 8px，行高 32–40px（`py-2`+`min-h`）；弹窗内边距 16–24px；卡片内边距 16px。
- 图标尺寸（lucide）：行内 14px（`size-3.5`）、常规 16px（`size-4`）、按钮 24px（`size-6`）、圆形操作按钮 36px（`size-9`）、插件图标 64px（`size-16`）。
- 移动端输入安全区 16px（`--text-mobile-input-safe`）。

### 3.5 图标

- **lucide 线性图标**（1.5–2px 描边、圆头端点），尺寸随上下文 12–64px。
- 图标永远携带语义色或 `foreground-subtle`，不单独使用多色图标。
- 加载中状态：`animate-spin` 旋转同一线性图标。

### 3.6 阴影、动效与背景质感

| 场景 | Light | Dark |
|---|---|---|
| 浮层（弹窗/菜单/气泡） | `0 2px 10px rgba(15,23,42,.08), 0 1px 2px rgba(15,23,42,.05)` | `0 1px 2px rgba(2,6,23,.6)` |
| Hero 欢迎页 | 线性渐变 `#eff6ff → #dbeafe → #bfdbfe` + 径向光斑（`mix-blend-screen`/`multiply`）+ `blur-3xl` | 深蓝紫渐变 `#060816 → #0b1333 → #12245a → #173474` + cyan/sky 光斑 |
| zai 主题 Hero | `#ffffff → #f8f8f8 → #ebf4ff` + `#80BEFF` 光斑 | `#161616 → #202020 → #001d3d` + `#4099FF` 光斑 |
| 示例 Prompt 卡片 | 半透明黑底 `bg-black/75` + `backdrop-blur-md` | 同左 |

- 动效原则：仅 `transition-colors`（悬停变色 150ms 级）、`transition-transform`（箭头旋转）、`animate-spin`（加载）。**无弹跳、无位移动画**，克制为主。

---

## 4. 主题系统

| 主题 | 说明 |
|---|---|
| `light` / `dark` | 跟随用户设置或系统（`system`），基于中性色阶语义 token |
| `zai-light` / `zai-dark` | 品牌主题：底色 `#f8f8f8`/`#161616`，强调蓝 `#0b7fff`/`#4099ff`，深藏青 accent `#ebf4ff`/`#001d3d` |

切换机制：根节点挂 `.dark` / 主题属性，全部 token 以 CSS 变量重载；渲染进程无硬编码色值。

---

## 5. 组件规范

> 以下基于对组件类名与结构的观察归纳，语义与 ZCode 一致。

### 5.1 按钮（Button）

| 变体 | 样式 | 用途 |
|---|---|---|
| `default`（主按钮） | `primary` 底色（Light 近黑 / Dark 近白）+ `primary-foreground` 反色文字，`rounded-md` | 主要操作（发送、安装、确认） |
| `outline` | 透明底 + `border` 描边，悬停 `hover:bg-hover` | 次要操作（取消、浏览） |
| `ghost` | 无底无描边，悬停 `hover:bg-hover` | 工具按钮（刷新、更多） |
| `destructive` | `destructive` 底色（或 ghost 变体 `text-destructive`），常用于确认弹窗 | 删除、卸载等危险操作 |

尺寸：`sm`（高 32px 级）、`lg`（高 40px 级）、`icon-lg`（40px 方形图标钮）。禁用态：`disabled` + 透明度降级。键盘焦点：`focus-visible:ring-2` + 品牌色 ring。

### 5.2 输入框

- 底：`input`（同卡片层）；描边 `border`；悬停 `border-hover`；聚焦 `ring-2 ring-input-border-focused`（= brand）。
- 典型输入区：多行文本输入 + 右侧主按钮；支持 `/` 命令与 `@` 文件引用的内联补全。

### 5.3 卡片 / 列表行

- 卡片：`rounded-xl` + `border` + `bg-card`；悬停 `hover:bg-hover`。
- 空状态：`rounded-xl border-dashed` + `foreground-subtle` 文案。
- 列表行：行高约 40px，左侧图标（`rounded-lg bg-surface` 容器）+ 标题/描述两行式布局。

### 5.4 弹窗 / 菜单 / 气泡

- 同一浮层层级（`card` 底 + 轻阴影 + `rounded-xl`），标题 `text-ui-lg font-medium`，底部操作区右对齐：次按钮 + 主按钮；危险操作用 `destructive` 变体并在标题区说明后果。
- 弹窗宽度常用 480px（`w-[min(480px,calc(100vw-2rem))]`）。

### 5.5 标签 / 徽标

- 底 `tag`（`#e6e6e6`/`#363636`）+ `rounded-full` + `text-ui-xs/sm`；类型标识色见 3.1.4。

### 5.6 Tooltip / Toast

- Tooltip：`tooltip` 底（同卡片层）+ `tooltip-foreground`（反色文字）+ 小圆角；标签式次要文字 `tooltip-tag-foreground`（60% 透明度）。
- Toast：`toast` 底（`#fff`/`#2b2b2b`）+ 轻阴影 + `rounded-xl`，语义色前缀图标（成功/警告/错误）。

### 5.7 代码 / 终端

- 代码块：Monaco 语法高亮（内置 ayu / catppuccin / material-theme 等多套），行内代码 `rounded` + 弱底色。
- 终端：`terminal-bg`（= background）+ ANSI 16 色（见 3.1.7）+ `terminal-cursor` 块状光标；等宽字体栈。

---

## 6. 交互原则

### 6.1 内容与过程可视化

1. **Markdown 优先**：Agent 输出一律以 GFM Markdown 渲染（代码高亮、表格、列表、引用、任务清单、数学公式 KaTeX、图片）；代码可复制、文件可跳转。
2. **工具调用全程透明**：每次工具调用独立成卡片——工具名 + 参数 + 进行中 spinner → 结果预览（成功/失败带色）；失败就地展示错误并提供重试，不静默吞错。
3. **流式呈现**：模型输出与工具执行状态实时流式更新，不做整块闪现；加载态用 `animate-spin` 图标 + 文案说明。

### 6.2 权限与安全

4. **权限分级**：`plan`（仅规划）/ 授权编辑 / 完全自主 等模式，切换有明确 UI 反馈；敏感操作（删除、推送、外部发布）必须用户确认。
5. **破坏性操作二次确认**：危险按钮用 `destructive` 变体，弹窗说明影响范围，确认按钮才可执行。
6. **独立权限面板**：系统级控制（如计算机控制 CUA）走独立权限窗口，不内嵌于主界面，避免误授权。

### 6.3 高效与可恢复

7. **键盘驱动**：Tab 补全、回车发送、`/` 唤起命令/技能、Esc 关闭浮层；所有交互均有键盘等价路径。
8. **引用即链接**：文件路径渲染为可点击链接（跳转打开）；代码行内评论（`::code-comment`）锚定到具体文件与行号；URL 直接可点。
9. **状态持久化**：会话历史可恢复、窗口位置尺寸记忆、自动更新（后台检查、重启生效）、设置即改即存。

### 6.4 容错与引导

10. **错误内联**：错误发生在哪一步就显示在哪一步（来源刷新失败、插件状态降级等均有内联警示条），并附"重试/更新"操作。
11. **空状态引导**：用虚线卡片 + 说明文案替代空白；欢迎页（Hero）展示示例 Prompt，一键填入输入区。
12. **多语言**：`en-US` / `zh-CN` 双语言，文案全部走 i18n（react-intl），界面中不硬编码字符串。

---

## 7. 技术栈（已确认）

| 层 | 技术 |
|---|---|
| 桌面壳 | Electron（asar 打包，`app-update.yml` 自动更新，`node-pty` + `ssh2` 原生模块） |
| UI 框架 | React 18 + 函数组件/Hooks |
| 状态管理 | Zustand（selector 式取数，持久化） |
| 样式 | Tailwind CSS v4（CSS 变量 token 体系，oklch/`color-mix` 色彩科学，无运行时 CSS-in-JS） |
| 国际化 | react-intl（en-US / zh-CN） |
| 图标 | lucide-react（线性图标） |
| 编辑器/代码高亮 | Monaco Editor（VSCode 同源，含多套语法主题） |
| 文档预览 | pdfjs-dist；docx / xlsx / pptx 预览引擎（Web Worker + WASM） |
| 数学公式 | KaTeX |
| 图表 | 通用图表库（Cartesian 系）+ cytoscape（架构/关系图） |
| 拖拽 | @dnd-kit |
| 终端 | xterm 风格终端 + node-pty（本地）/ ssh2（远程） |
| 调试辅助 | playwright-core（录制/检查工具） |
| 辅助进程 | CUA（"ZCode Computer Use" 辅助 App，macOS AX 原生模块），SSH、调度器（scheduler）等独立进程 |
| 进程结构 | `main`（主进程）/ `renderer`（UI）/ `host` / `scheduler` / `preload`（bridge） |

### 7.1 对 LayoutSee 的启示

- LayoutSee 若做 **Electron + Web 技术栈**：可直接复用同一套 Tailwind v4 token（复制 3.x 全部 CSS 变量即可 1:1 对齐）。
- 若做 **macOS 原生（SwiftUI/AppKit）**：按第 8 章映射为 `Color`/`NSColor` 与 `Font`，观感一致。

---

## 8. LayoutSee 对齐实施指南

### 8.1 Token 落地（SwiftUI 示例）

```swift
// 语义色（默认主题）
enum ZCodeColor {
    static let background   = Color(hex: 0xFAFAFA)  // dark: 0x171717
    static let panel        = Color(hex: 0xFFFFFF)  // dark: 0x171717
    static let card         = Color(hex: 0xFFFFFF)  // dark: 0x262626
    static let sidebar      = Color(hex: 0xF0F0F0)  // dark: 0x0A0A0A
    static let foreground   = Color(hex: 0x262626)  // dark: 0xE5E5E5
    static let fgSubtle     = Color(hex: 0x262626).opacity(0.6) // dark: 0xE5E5E5 @60%
    static let border       = Color(hex: 0x0D0D0D).opacity(0.10) // dark: white @10%
    static let brand        = Color(hex: 0x0EA5E9)
    static let destructive  = Color(hex: 0xEF4444)  // dark: 0xF87171
    static let success      = Color(hex: 0x22C55E)
    static let warning      = Color(hex: 0xF59E0B)
    static let hover        = Color(hex: 0x0D0D0D).opacity(0.05) // dark: white @10%
}
```

### 8.2 字体映射

| ZCode | macOS 原生 |
|---|---|
| `--font-sans` | `.system`（SF Pro）/ 中文 `.system`（PingFang SC 自动回退） |
| `--font-mono` | `.monospaced`（SF Mono） |
| 字号基准 14px | 直接使用 pt = px（非 Retina 逻辑像素） |

### 8.3 尺寸映射

| ZCode | 建议值 |
|---|---|
| 圆角 md/lg/xl | 6 / 8 / 12 pt |
| 间距栅格 | 4 pt 基准 |
| 列表行高 | 40 pt |
| 弹窗宽度 | 480 pt 上限 |

### 8.4 对齐检查清单（自测）

- [ ] 深色/浅色两套完整 token，切换不闪烁（跟随系统）
- [ ] 唯一强调色（brand），状态色仅用于语义
- [ ] 所有圆角 ∈ {4, 6, 8, 12, 16, 24}，间距 ∈ 4pt 栅格
- [ ] 图标全部线性风格、单一描边宽度
- [ ] 悬停态统一 `hover` 色，聚焦环统一品牌色 2px
- [ ] 破坏性操作 = destructive 色 + 二次确认弹窗
- [ ] 空状态用虚线边框卡片 + 引导文案
- [ ] 加载态统一 spinner，失败统一内联错误 + 重试
- [ ] 全部文案走 i18n（至少中英双语）
- [ ] 文件/行号/URL 渲染为可点击链接
- [ ] 终端用 ANSI 16 色标准语义

---

## 9. 附录：Token 速查表（zai 主题实色）

| 用途 | zai-light | zai-dark |
|---|---|---|
| 背景 | `#f8f8f8` | `#161616` |
| 侧栏 | `#f0f0f0` | `#161616` |
| 面板/头部 | `#ffffff` | `#202020` |
| 卡片/输入/浮层 | `#ffffff` | `#2b2b2b` |
| 标签/次级 | `#e6e6e6` | `#363636` |
| 主蓝 | `#0b7fff` | `#4099ff` |
| 亮蓝 | `#80beff` | `#80beff` |
| 深藏青 accent | `#ebf4ff` | `#001d3d` |
| 错误 | `#e03131` | `#ff5c5c` |
| 成功 | `#1e8a3e` | `#46bf72` |
| 警告 | `#e07b00` | `#ff8a30` |
| 新增(Git) | `#1e8a3e` | `#46bf72` |
| 修改(Git) | `#e07b00` | `#ff8a30` |
| 删除(Git) | `#e03131` | `#ff5c5c` |
