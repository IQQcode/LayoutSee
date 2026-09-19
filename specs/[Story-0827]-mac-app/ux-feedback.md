# Story-0827 UX 体验反馈修复记录

时间：2026-08-29。本轮为体验优化专项（功能缺陷已在 bugs.md 关闭），共 8 项，涉及投屏观感、表单预填、布局自适应与视觉风格对齐 hugeicons / ZCode。

## 五轮（09-18）：表格灰条根因 + iOS / HarmonyOS 预告 Tab

### 1. 表格「操作」列那条灰底（图一 ①）

**不是边框、不是投影——是半透明 hover 底色的两层叠加。**

排查过程：先用 `getComputedStyle` 看到行与操作列都算出 `rgba(29,29,31,.05)`，与卡片底色 `#fcfcfd` 相同，看不出问题；把窗口压到 1000px 触发横向滚动、再模拟 hover，截图像素比对才复现——`.row-actions` 是 `.table-row` 的子元素，**父子各画了一层 5% 黑**，于是粘性操作列约等于 10% 黑（明显灰条），而行其余部分只有 5%（几乎看不出）。窄窗 + 鼠标在行上时必定出现，正是用户看到的现象。

修复：行底色改用**不透明** token（`--ls-color-row-bg` / `--ls-color-row-bg-hover`，hover 值由半透明色与面板色合成算得：浅色 `#f0f0f1`、深色 `#2e2e30`）；行内粘性列 `background-color: inherit` 直接跟随行，永远不会叠加出第二种色。验证：默认态与 hover 态两侧背景值完全相等（`rgb(252,252,253)` / `rgb(240,240,241)`）。

### 2. iOS / HarmonyOS 预告 Tab（图一 ②）

设备页平台 Tab 从「只有 Android」扩为 **Android / iOS / HarmonyOS**，后两者标 `预告` 徽标；切换只展示提示文案，**不做任何功能实现**（按需求）。

占位面板（`features/devices/PlatformPlaceholder.jsx`）的元素与文案：

- 平台字形（iOS 苹果 / HarmonyOS 六边形）+ 外圈脉冲光环 + 呼吸柔光；
- 标题：`iOS 支持正在路上` / `HarmonyOS 支持正在路上`；
- 光泽提示行：`设备接入 · 敬请期待`；
- 说明段：iOS 讲「沿用同一套快照与元素模型，正在设计中」，HarmonyOS 讲「调试链路差异较大，Android 体验稳定后单独评估」——如实说明进度，不承诺时间；
- `返回 Android` 按钮 + 「以上能力当前仅对 Android 设备开放」脚注；能力清单列出四项待开放能力。

### 3. 动画（参考 reactbits，纯 CSS 落地）

参考 [reactbits](https://reactbits.dev) 的 **BlurText**（逐词模糊解析）与 **ShinyText**（金属光泽扫过）：

- 两者原实现都依赖 `motion/react`；效果本身可纯 CSS 表达，故**不引入 motion/gsap**，用 `@keyframes` + 逐词内联 `animation-delay` 复刻，包体零增长；
- 标题错峰 90ms（短句有节奏感），说明段 26ms（长段落不拖沓，约 1s 内读完）；
- 光泽行用 `background-clip: text` + 渐变位移实现；
- 全部动画在 `prefers-reduced-motion: reduce` 下降级为静态（blur 与外发光全关，光泽行退回纯文本色）。

验证：headless 逐秒采样 —— 300ms 落定 0 个词、1200ms 3 个、2000ms 全部 7 个词 `opacity:1 / blur(0px)`；延迟序列确认为 `0,90ms` 与 `0,26,52,78,104ms`。

### 4. 顺带修掉的隐患

`Button` 的 `icon` 只接受组件，传 Lucide **图标数据**（数组）会抛 React #130 白屏——占位页的「返回 Android」就这么炸过一次。现在 `Button` 自动识别数组并按数据渲染 `MorphGlyph`，同类错误不会再出现（此前 `IconButton` + `GearSix` 已踩过一次）。

### 验证

灰条两侧背景值相等、三个 Tab 切换正常（含 `返回 Android` 回到表格）、动画按预期推进并落定、页面零报错；Web lint + 构建通过，全量单测除 `core/summary.py` 的既有报错外全绿（见下）。

---

## 四轮（09-18）：左侧图标接入 morphicons 形变动画

### 目标

左侧 UI 图标改用 [morphicons](https://www.morphicons.com/)（MIT，`npm i morphicons`）：任意两个描边图标之间做**弹簧形变**，状态切换从「换一张图」变成「形状自己转过去」。

### 选型结论

- morphicons 只吃**描边中心线**图标数据（Lucide / Tabler / Heroicons outline / Iconoir）。Phosphor 是填充型，**不能用于 morph**（文档明确：filled 图标能解析但过渡中形变不正确）。因此左侧图标统一换成 **Lucide 数据**（`import { Camera } from "lucide"` 是数据不是组件）。
- 用法极简：`<MorphIcon icon={state ? B : A} />`，换 prop 即动画，不需要 from/to、key 或 AnimatePresence。
- 体积：核心 6.6 KB gzip，零运行时依赖，tree-shaking 后整包 **+12.5 KB gzip**（130.78 → 143.31 KB）。

### 形变设计（图标含义与动作一一对应）

| 位置 | 静止态 | 目标态 | 触发 |
|---|---|---|---|
| 抓取布局快照 | Camera | LoaderCircle（旋转）→ CircleCheck | 抓取中 / 完成后 1.8s 回位 |
| 冻结画面 | Snowflake | Sun | 冻结↔解冻 |
| 只读模式 | Lock | LockOpen | 只读↔可写 |
| 审查模式 | Crosshair | MousePointerClick | 进入↔退出 |
| 音量增大 | Volume1 | Volume2 | 点击脉冲（音量档位上升） |
| 音量减小 | Volume2 | Volume1 | 点击脉冲（音量档位下降） |
| 旋转屏幕 | RotateCw | RotateCcw | 每次点击交替（对应设备下次旋转方向） |
| Tab 常用 | LayoutGrid | LayoutDashboard | 选中时 |
| Tab 元素查看 | Code | CodeXml | 选中时 |
| Tab MCP | Plug | PlugZap | 选中时 |
| Tab 插件 | Puzzle | Blocks | 选中时 |
| Tab 布局智能 | Sparkle | Sparkles | 选中时 |
| 侧边导航 | Smartphone / LayoutGrid / Cog | SmartphoneCharging / Grid2x2Check / Settings2 | 激活时 |

另外顺手修掉了上一轮的图标重复：原「最近任务/常用」都是宫格、「审查/元素查看」都是放大镜，现在 16 个控制轨图标**互不重复**。

### 实现要点

- 新增 `repos/web/src/components/MorphIcons.jsx` 作为唯一图标入口：`glyphs` 集中导出 + `MorphGlyph` 统一 19px/线宽 2/`reducedMotion="user"`（跟随系统「减弱动态效果」，与设计规范一致）。
- 依赖：`morphicons@1.7.1` + `lucide@1.47.0`（都是 repos/web 的 dependencies）。
- `IconButton` 的 `icon` 改为可选，尾随 MorphGlyph 走 children，标题栏齿轮一并换到同一套。
- CSS 只补旋转（`.morph-glyph.is-spinning`）与减弱动效降级；形状插值全部由库负责。

### 验证（headless DOM + 路径采样）

- 16 个控制轨按钮全部渲染 `svg.morph-glyph`，页面零报错；
- **确认动画真的在插值**：只读按钮点击后 path 长度 237 → 3337 → 3369 → 3367 → 658 连续变化后落定（弧长重采样中间态），审查模式 12 次采样得 5 个不同中间帧；
- 抓取三态：点击后 `is-spinning=true`，完成后旋转停止且按钮进入 active；
- Tab morph：仅选中态变化的两个图标发生形变，其余保持原路径；
- 全量单测（Core 34 / 契约 7 / Web 10 / 壳 8）+ lint + verify:artifacts 通过。

### 已知边界

右侧任务面板内的行内按钮图标（刷新/查询/导出/重置/启动/停止应用等）仍是 Phosphor。它们与左轨尺寸、语境不同，暂未迁移；若要求全站统一，后续可一并换成 Lucide。

---

## 三轮（08-30）：顶部 padding 根因 + 对齐精修

### 1. 窗口顶部多余 padding（图一 ①）——根因终于铲除

工程**一直没有全局 CSS reset**，`body` 保留浏览器默认 `margin: 8px`——窗口四周那条白边从第一版就存在，之前所有"满幅/去黑边"的修复都叠在它上面。本轮补齐 reset（`html/body margin 0 + height 100%`、`box-sizing: border-box`、`body overflow hidden`），窗口内容完全贴边。

### 2. 顶部重叠进一步收敛（图一 ②）

标题栏高度 **56 → 48px**（按要求减 8px），交通灯位置同步调整为 `{x:18, y:16}` 在新高度内垂直居中；配合上轮的标题栏结构，系统按钮/标题/返回/info-bar 各归其位。

### 3. 「操作」表头与「控制」按钮中心对齐（图三）

上一轮 sticky 右缘对齐时表头与按钮宽度不同导致中心偏差 42px。本轮两者统一为 **同宽 150px 列内 flex 居中 + sticky right 12px**：无论是否横向滚动，中心恒定对齐，且距窗口右缘保留 12px 内边距。headless 实测中心偏差 **0px**。

### 4. 选中高亮只保留当前（图四）

点选新元素时清掉上一个的红色高亮（替换式）：`selected` 类高亮全量替换，XPath/诊断高亮不受影响。树行点击与画布点选统一走 `selectNode`。

### 5. 附带修复

- 设备信息栏小窗防裁剪：gap 22→14、`overflow: hidden`、设备名/序列号超长省略号、设备切换下拉 `max-width: 150px`——窄宽度下不再把下拉裁出界。

### 三轮验证

headless 断言：`body margin 0`、标题栏 48px 且距窗口顶部 0、选第二个节点后红色线框数=1、表头/按钮中心偏差 0px；全量单测与 lint 通过。

---

## 二轮（同日下午）：交互预期精修 6 项

## 二轮（同日下午）：交互预期精修 6 项

### 1. 选中元素红色高亮（图一 ①）

布局查看与审查模式下，选中元素线框由蓝色改为**红色**（`--ls-color-danger`），边框粗细（1px）与蒙层透明度（12%）与其他状态保持一致，蓝=定位、红=选中语义清晰。

### 2. 属性面板 resource-id 置顶（图一 ②）+ Tab 顺序（图一 ③）

- 属性列表顺序调整为 **resource-id → nodeKey → className → bounds → 其余原始属性**；resource-id 为空时不占行；
- 工作台 Tab 顺序改为 **常用 → 元素查看 → MCP → 插件 → 布局智能**（左侧控制轨同步）。

### 3. 工作台顶部重叠彻底解决（图二，对齐图五排版）

此前仅加 34px 顶距，info-bar 仍与交通灯同排。本轮按图五排版重构：工作台顶部新增**标题栏**（交通灯区 + 「LayoutSee V0.1」品牌区，与设备管理页同款样式，可拖拽移动窗口），标题栏下方才是控制轨 / 设备信息栏 / 任务面板——rail 顶部 y=56、info-bar 顶部 y=56，任何窗口尺寸下互不重叠。

### 4. 设备管理页细节（图六）

- 侧边导航「设备/群控/设置」**去掉文字下划线**（NavLink 默认样式）；
- 操作列与「控制」按钮对齐：去掉上一轮引入的 `padding-left`（按钮前的多余留白），保留 sticky 吸右与渐变阴影。

### 5. 投屏区白边/黑线清零（图三）

live 模式画面**满幅贴合**：viewport 留白 14→0px、frame 边框/圆角/阴影全部去除，画面即面板边界；并且流建立后**设备区宽度自动适配画面比例**（每台设备仅首次，手动拖过分隔条则尊重手动值），把 letterbox 空白压到最小。快照查看模式保留轻边框与呼吸边。

### 6. 提示气泡被遮挡（图四）

控制轨按钮的 tooltip 被 layout 查看模式后的设备画布盖住——控制轨未建立层叠上下文所致。修复：`.control-rail { position: relative; z-index: 30 }`，tooltip 恢复显示。
（注：图四中出现的是 Comate 的「添加到当前任务」系统级悬浮条，属第三方工具窗口层级问题，LayoutSee 侧无遮挡行为。）

### 二轮验证

headless DOM 断言：标题栏 56px 且 rail/info-bar 顶部 y=56、Tab 顺序正确、带 resource-id 节点属性行顺序 `resource-id → nodeKey → className → bounds`、live frame border 0、红色选中规则注入；Web lint + 构建通过。

---

## 一轮（同日上午）：8 项体验优化

## 1. 投屏区黑边去除（图一 ①②）

- **现象**：画面顶部有黑色横条（①），底部出现横向滚动条（②），原生 scrcpy 无此问题。
- **根因**：canvas 元素自带黑色背景（letterbox 区域透黑）；画面尺寸用 `round` 计算可能超出容器 1px，触发 device-stage 横向滚动条。
- **修复**：live 模式 canvas/frame 背景改透明（画面外区域显示画布底色）；`device-stage` 加 `overflow: hidden`；画面尺寸 `round → floor`（永不溢出）；快照查看模式保留面板底色。

## 2. 启动应用默认预填当前前台应用（图一 ③）

- 常用 Tab 读取前台应用成功后，若「启动应用」表单为空则自动填入当前包名与 Activity（用户已手动输入时不覆盖），placeholder 更新为「默认填入当前前台应用」。
- 验证：真机贴吧前台时自动填入 `com.baidu.tieba` / `com.baidu.tieba.forum.ForumActivity`。

## 3. 工作台顶部导航与红绿灯重叠（图二 ①）

- **根因**：`hiddenInset` 标题栏的交通灯浮在窗口左上（y≈20），而工作台内容从 y=0 开始。
- **修复**：`.workspace-page` 增加 `padding-top: 34px`，控制轨与设备信息栏整体下移，不再与交通灯重叠。

## 4. 控制轨图标去重 + 语义化 + hover 过渡（图二 ②）

对齐 hugeicons「图标含义与功能一一对应」的要求，Phosphor 图标重新分配并消除重复：

| 功能 | 原图标 | 新图标 |
|---|---|---|
| 最近任务 | SquaresFour（与常用 Tab 重复） | Rows |
| 旋转屏幕 | ArrowClockwise | ArrowsClockwise |
| 抓取布局快照 | VideoCamera（含义误导） | Camera |
| 审查模式 | MagnifyingGlass（与元素查看 Tab 重复） | Crosshair |
| Tab：常用/插件/元素/MCP/布局智能 | 仅 common 有图标且与他处重复 | SquaresFour / PuzzlePiece / Code / PlugsConnected / Sparkle |
| 重置（元素工具栏） | 无图标 | ArrowsCounterClockwise（与抓取 ArrowClockwise 区分） |

hover 过渡：上浮 1px + 放大 7% + 阴影（弹性曲线），按下回缩 7%，tooltip 淡入左移进场；侧边导航项 hover 时图标微放大、按下回缩。

## 5. 任务 Tab 改 Liquid Glass 胶囊样式（图二 ③，参考 hugeicons 官网）

- Tab 容器改为悬浮胶囊：14px 圆角、毛玻璃（`backdrop-filter: blur(14px) saturate(1.5)`）、半透明面板底、内高光描边；
- 激活项为浮起的圆角卡片（白底 + 双层阴影 + 上移 1px），非激活项 hover 出现浅色 pill；
- 切换过渡：背景/颜色/阴影/位移全部 180ms 缓动，按下有回缩反馈；深色主题单独调阴影。

## 6. 设备表格「操作」列对齐与吸右（图五 ①）

- 表头「操作」文字右对齐（`justify-self: end`），与「控制」按钮对齐；
- 操作列（表头 + 单元格）`position: sticky; right: 0` + 面板底色 + 左侧渐变阴影：窗口再窄、行再长，操作按钮始终贴右可见，中间列自适应展示。

## 7. 侧边导航对齐 hugeicons 菜单样式（图五 ② / 图三）

- 导航项加高至 38px、12px 圆角 pill、字重 500、图标与文字间距加大；
- hover 出现 pill 底色且图标微放大（180ms 弹性过渡），按下回缩；激活项蓝底 pill 加粗。

## 8. UI 层级树支持横向滚动（图六）

- 长属性行不再被 ellipsis 截死：树行宽度按内容撑开（`width: max-content; min-width: 100%`），`.tree-scroll` 双向滚动，可横滑查看完整 resource-id / text。

## 验证

- headless DOM 断言：启动表单预填值、task-tabs `backdrop-filter` 生效、控制轨 16 按钮（新图标）、层级树 74 行、树容器 `overflow-x: auto`；
- Web lint + 构建通过；全量单测（Core 34 / 契约 5 / 壳 8 / Web 4）全绿。
