# Story-0827 UX 体验反馈修复记录

时间：2026-08-29。本轮为体验优化专项（功能缺陷已在 bugs.md 关闭），共 8 项，涉及投屏观感、表单预填、布局自适应与视觉风格对齐 hugeicons / ZCode。

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
