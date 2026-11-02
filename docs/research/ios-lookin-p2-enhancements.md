# iOS Lookin P2 能力调研：3D 分层视图 / 逐节点图片 / resource-id

> 调研日期：2026-10-27。前置：v22.7.0 路线 A（纯 Python 复刻 Lookin 协议）已落地并完成展示层补完（画布绝对坐标、Lookin 风格属性面板、ivar 名、模拟器截图底图，见 `specs/22_7_ios_lookin/summary.md` 展示层补完轮）。本文评估三项 P2 增强能力的可行性与方案，**只调研不落地**。

## 一句话结论

三项全部可行，且 **resource-id 有一条零改动路线（206 InvokeMethod）**，比原设想的 fork LookinServer 便宜得多。推荐顺序：resource-id（0.5–1 天）→ 逐节点图片（1.5–2 天）→ 3D wireframe（1 天）→ 3D 图片纹理（0.5–1 天），**合计约 3.5–5 人天**。逐节点图片是 3D 图片纹理的前置。

## 协议事实（2026-10-27 依 LookinServer @develop 源码逐一核实）

| 请求 | 事实 | 源码位置 |
|---|---|---|
| 202 Hierarchy | 静态树 `itemsWithScreenshots:NO attrList:NO`——永不带图、不带属性组；另存在 `exportedInfo`（带图+低质量+全属性）但仅服务于本地导出文件功能，无独立请求入口 | `LookinHierarchyInfo.m` staticInfo/exportedInfo |
| 203 HierarchyDetails | **按 oid 定点的任务包流式协议**：请求为 `Array<LookinStaticAsyncUpdateTasksPackage>`，每个 task `{oid, taskType(0 无图/1 solo/2 group), attrRequest(0 自动/1 需要/2 不需要), needBasisVisualInfo, needSubitems, clientReadableVersion}`；响应按包流式返回 `LookinDisplayItemDetail {displayItemOid, soloScreenshot, groupScreenshot, attributesGroupList, frame/bounds/hidden/alpha, subitems, failureCode}`，`failureCode=-1` 表示图层已释放 | `LKS_HierarchyDetailsHandler.m`、`LookinStaticAsyncUpdateTask.h`、`LookinDisplayItemDetail.h` |
| 203 图片渲染 | 恒全质量（`lowImageQuality:NO`，203 路径未透传低质量参数）；容器用 `drawViewHierarchyInRect:afterScreenUpdates:YES`（快速快照 API），无 host view 时 `renderInContext:`；**主线程逐包处理**（dispatch main queue），大批量会阻塞被测 App UI；尺寸上限 `LookinNodeImageMaxLengthInPx = 16384px`（超限降采样）；**solo 图仅对有 sublayers 的视图有意义，叶子节点返回 nil** | `LKS_HierarchyDetailsHandler.m:64-119`、`CALayer+LookinServer.m:46-149`、`LookinDefines.h:160` |
| 206 InvokeMethod | **远端无参 selector 任意调用**：请求 `{oid, text(selector 字符串)}`，从对象注册表取目标 → `NSSelectorFromString` → `respondsToSelector` 校验后 NSInvocation 执行；**带参方法直接拒绝**（`numberOfArguments > 2`）；**无 selector 白名单**；返回 `{description(结果字符串化), object(结果对象 LookinObject)}`，NSString 结果直接落在 description | `LKS_RequestHandler.m:199-238, 328-380` |
| 208 FetchImageViewImage | 严格限定 `UIImageView.image`（强转校验），返回 PNG 字节——只适合看图片内容，**不能渲染任意视图** | `LKS_RequestHandler.m:246-263` |
| 自定义属性 | App 侧实现 `lookin_customDebugInfos` / `lookin_customDebugInfos_0..4` 方法即可在属性面板出现自定义分组——是 **App 代码路径**，不存在「不 fork 也不改 App」的 a11y 注入点 | `LKS_CustomAttrGroupsMaker.m:44-52` |
| 官方客户端 203 分包 | 分包按**面积感知 + 数量上限**：`packageMaxArea = 2,000,000 px²`（task.frameSize 累加）、`packageMaxTasksCount = 100`；task 的 oid 取 `layerObject.oid` | `LKStaticAsyncUpdateManager.m:177-206` |
| 官方客户端图片时机 | **常规全量刷新 taskType = NoScreenshot（不拉图）**；图片只在单节点重载时按需拉：`doNotFetchScreenshotReason == Permitted` 时发 group 图 task，若节点可展开（isExpandable）再加一个 solo 图 task；依赖 LookinServer ≥ 1.2.7（客户端显式校验并提示升级） | `LKReloadItemAndChildrenUpdateTaskMaker.m:29`、`LKReloadSingleItemUpdateTaskMaker.m:29-49` |
| 官方画布纹理选择 | `appropriateScreenshot`：**展开的容器用 solo 图，折叠/叶子用 group 图**（3D 展开态必须用 solo，否则容器 group 图会盖住子层平面） | `LookinDisplayItem+LookinClient.m:57-61` |
| 官方 3D 实现 | **SceneKit**：每节点一个 SCNPlane（+border/mask 节点），相机 `focalLength = 20 + scale² × 730`，层距 `zInterspace` 2D 恒 0.01、3D = 0.1 + z×0.7，按 zIndex 排布并加偏移防平面重叠渲染 bug；2D/3D 切换 = rotation 归零与保留 | `LKPreviewView.m:155-176, 330-345`、`LKDisplayItemNode.m:18-58` |
| 官方 frameToRoot 公式 | `child.frame.origin − 父级 bounds.origin + 父级 frameToRoot`（递归）；bounds.origin ≠ 0 的滚动容器必须扣除该偏移，否则滚动内容整体错位 | `LookinDisplayItem+LookinClient.m:88-104` |
| 官方 206 用法 | 仅用于 Dashboard 的「方法搜索调用」交互功能（用户输入 selector 后远程执行） | `LKDashboardViewController.m:453` |
| 已知限制（不变） | LookinServer 属性组不含 accessibilityIdentifier/Label（Blueprint 无此属性，grep 零命中）；单客户端独占；主线程处理（抓取期间 App UI 有感知） | — |

另：我们现有 `client.hierarchy_details()` 已实现 203 的分批读骨架（`dataTotalCount/currentDataCount` 聚合），但其 `merge_hierarchy_details` 会 `_strip_image_fields` 丢弃全部字节——图片流需要改为按需保留，属改造而非新建。

## 方案设计

### 1. resource-id（accessibilityIdentifier / accessibilityLabel）——推荐 206 路线

**推荐：206 InvokeMethod 零改动读取**。`accessibilityIdentifier`/`accessibilityLabel`/`accessibilityValue`/`accessibilityHint`/`accessibilityTraits` 全部是无参 getter，可在 202 层级抓取后对每个节点的 viewObject oid 远程调用。被测 App **无需任何改动**（不 fork、不加代码），沿用 stock LookinServer 1.2.8。

- 调用量级：232 节点 × 1–2 个 selector ≈ 250–460 次调用，主线程逐次执行。模拟器实测 210 单次往返 2–5ms 量级，全量预计 1–3s；真机 usbmux 隧道 RTT 更高。**决策点**：identifier 全量拉（Agent XPath 依赖它）、label 惰性（选中节点时拉），或二者都全量——实测后再定。
- 安全约束：selector 由 Core 固定白名单下发（不透传用户输入）；只调用无参 getter，规避副作用方法（如 `accessibilityElements` 会触发懒加载建树，禁入白名单）。
- 落点：`driver._capture` 在逐节点 210 之后串行/小并发调用 206 → 结果并入 `ATTR_EXTRACTION_RULES` 的 resource-id / content-desc 提取 → XML 与 extras 全链路（XPath/选择器/摘要/诊断/MCP）自动受益。
- **备选（仅当 206 批量性能不可接受时启用）**：fork LookinServer（MIT 合规），在 `LookinDashboardBlueprint` 增加 a11y 分组（groupID/sectionID/attrIDs + getter 映射表），属性组随 210 批量返回；代价是被测 App 必须把依赖换成 fork 版（采纳摩擦），且承担 fork 维护。fork diff 本身很小（一张 Blueprint 常量表 + 属性名），真正成本在 App 侧依赖切换。

### 2. 逐节点图片——203 定点任务包，**按需优先（官方同款），全树为可选增强**

原设想「needImages/208」不准确：needImages 只控制 App 缩略图（161×350，已验证过糊），208 仅 UIImageView。正解是 203 的任务包协议按 oid 定点拉取。**官方客户端的行为给出了粒度答案：常规刷新不拉图（NoScreenshot），图片只在单节点重载时按需取**——因此 v1 以「选中节点按需拉图」为主体（与官方一致），「全树深度抓取」降为可选增强（官方从未做全树带图，主线程时长风险需自担）：

- **选中节点按需（v1 主体）**：选中某节点时发 task 拉它的 group 图（亚秒级），用于属性面板「所见」、画布局部核对与 3D 纹理；节点可展开时同批加 solo 图 task（3D 展开态纹理需要，见下）。分包参数直接对齐官方：单包累计面积 ≤ 2,000,000 px²、任务数 ≤ 100。
- **全树深度抓取（可选增强）**：工具栏显式动作，对全树按官方分包参数发 203；预期全树 228 节点 10–30MB PNG、3–10s。是否排入 v1 由实测定夺。

- 落点（core）：`client` 新增 203 请求编排（复用分批读骨架，去掉图片丢弃逻辑；请求侧编码 LookinStaticAsyncUpdateTasksPackage 用现有 `encode_keyed_object` 模式，编码键按 `LookinStaticAsyncUpdateTask.m` 校准）；图片字节按 displayItemOid 存内存缓存 `{snapshotId: {nodeKey: png}}`，**不进快照 JSON**（避免 record 膨胀 10–30MB）；新增 `GET /api/v1/snapshots/{id}/nodes/{key}/image` 端点（Host/Origin/会话校验与既有一致）。
- 落点（web）：属性面板「所见」图 + 画布「图像模式」开关（线框之上叠真实截图纹理），`<img>` 懒加载逐节点请求。
- 与 simctl 底图的关系：底图是全屏静态 PNG（已落地）；逐节点图提供**分层真实渲染**（可做遮挡分析、单独视图查看、3D 纹理），二者互补不互替。

### 3. 3D 分层视图——web CSS 3D，分两阶段（官方为 SceneKit，概念可直接映射）

官方 3D 是 SceneKit 场景（每节点一个 SCNPlane + 相机 + 层距），其参数为 web CSS 3D 提供了直接映射：相机 `focalLength = 20 + scale² × 730` ↔ CSS `perspective`；层距 `zInterspace`（2D=0.01 / 3D=0.1+z×0.7）↔ `translateZ(depth × 步长)`；rotation CGPoint（弧度，2D 切换即归零）↔ `rotateX/rotateY` 状态。核心交互复刻完全可行：

- **阶段一（wireframe 版，数据已齐）**：`.device-frame` 加 `perspective`，快照节点层加 `transform-style: preserve-3d; transform: rotateX(θ) rotateY(φ)`，每个线框 div 追加 `translateZ(depth × 步长)`。228 个绝对定位 div 无性能压力；浏览器合成器原生处理 3D 深度排序；**DOM 命中在 3D 变换下仍生效**——但现有 `hitTest`（boundingRect 反算 nx/ny）在旋转后失效，需改为以事件 target 上的 `data-node-key` 直接命中（更简单也更准）。交互：拖拽旋转（pointer 事件已有基础）、滚轮缩放、2D/3D 切换按钮（对齐官方语义：切 2D 时旋转归零、切 3D 保留当前角度）、重置。分层维度 v1 按 depth（层级树深度）。
- **阶段二（图片纹理，依赖第 2 项）**：纹理选择对齐官方 `appropriateScreenshot` 语义——**展开的容器用 solo 图、折叠/叶子用 group 图**（否则容器 group 图会盖住子层平面，3D 分层失去意义）；懒加载；「图像模式」开关对齐 Lookin。
- 落点：DeviceCanvas 新增 snapshot 内 3D 开关（不动 live 模式）；CSS 新增 `preserve-3d` 相关规则；WorkbenchPage 无需新状态（开关收敛在画布内）。
- 备选方案 three.js/WebGL 否决：引入渲染依赖、与既有 DOM 树选择/联动机制割裂，CSS 3D 足够。
- 环境支持：Electron 44（Chromium）与主流浏览器对 `preserve-3d` 支持成熟，无兼容风险。

## 改动点清单

| 工程 | 改动 | 说明 |
|---|---|---|
| `repos/core` `ios/client.py` | 新增 `invoke_method(oid, selector)`、`hierarchy_details_packages(packages)`（203 定点编排） | 206 参数 `{oid, text}`；203 分批复用现有骨架，图片字节保留 |
| `repos/core` `ios/driver.py` | capture 流程并入 206 批量 a11y 读取（固定白名单）；`ATTR_EXTRACTION_RULES` 增 resource-id/content-desc 来源 | 失败静默，量级实测后定全量/惰性 |
| `repos/core` `snapshots.py` + `server.py` | 图片内存缓存 + `GET /snapshots/{id}/nodes/{key}/image`；「深度抓取」触发入口（或复用 snapshots POST 带 `depth=true` 参数） | 不进快照 record；快照 TTL 同步清理缓存 |
| `repos/contracts` | 新端点/参数契约 + 生成物 | `contracts:check` 门禁 |
| `repos/web` `DeviceCanvas.jsx` + `app.css` | 3D 开关 + preserve-3d 渲染 + 拖拽旋转/缩放 + target 命中改造；图像模式叠加 | 2D 路径不动 |
| `repos/web` `ElementTab.jsx` / `attrFormat.js` | 属性面板「所见」图（选中按需拉取）；ivar 徽标旁可显示 resource-id | 复用既有分组渲染 |

## 工作量与实施顺序

| 阶段 | 内容 | 估算 |
|---|---|---|
| P2-a | resource-id：206 编排 + 白名单 + 提取规则 + 单测（206 响应金样） | 0.5–1 天 |
| P2-b | 逐节点图片：203 定点编排（选中按需为主）+ 请求编码校准 + 缓存/端点 + web 加载 | 1.5–2 天 |
| P2-c | 3D wireframe：CSS 3D + 交互 + 命中改造 | 1 天 |
| P2-d | 3D 图片纹理（solo/group 选择对齐官方）+ 图像模式 | 0.5–1 天 |
| **合计** | （b 是 d 前置；a 独立可先行） | **约 3.5–5 人天** |

## 官方客户端源码核验记录（2026-10-27，/Users/jiazihui/Documents/Temp/lookin/Lookin）

调研期间用 GPL 的官方 mac 客户端源码（只读理解行为，不复制代码）核验了本文件全部关键论断，并有一项意外收获：官方 `calculateFrameToRoot` 公式（`frame.origin − 父级 bounds.origin + 父级 frameToRoot`）暴露出 v22.7 展示层补完轮 driver 坐标累加**缺少「减父级 bounds.origin」**——滚动容器（UIScrollView contentOffset，bounds.origin ≠ 0）里的子节点画布位置会整体偏移。已按官方公式修复（`driver._build_node`）并以单测锚定（`test_build_xml_subtracts_parent_bounds_origin`）；bounds.origin=0 时行为不变，实弹滚动态待用户滚动列表后自然核对。同时 `isCustomClass` 对齐官方 `representedForSystemClass`（`_` 前缀归系统类）。

## 风险与开放问题

1. **206 批量主线程时长**：460 次逐包调用虽小但都占用被测 App 主线程；若实测 >3s，降级为「identifier 全量 + label 惰性」或「可交互节点优先」。P2-a 第一天先实测定参。
2. **203 大包主线程阻塞**：服务器主线程逐包渲染；分包步进 + 包间让出（等上一包响应再发下一包，现有分批读骨架天然如此）可控。
3. **图片内存占用**：全树 10–30MB 驻留 Core 进程；快照 TTL（600s）与 KEEP_PER_DEVICE=3 淘汰时同步清理，否则上限 ~90MB——需在实现时对齐 store 淘汰钩子。
4. **3D 下既有交互回归**：审查模式点击、XPath 高亮联动依赖 2D hitTest；3D 模式改 target 命中后两条路径需各自验证（高亮 overlay 仍按 2D 百分比定位，旋转时随容器变换，无需特殊处理）。
5. **a11y 数据质量**：被测 App 若未认真设置 accessibilityIdentifier（常见于纯 frame 布局业务），resource-id 仍大面积为空——206 路线只能「如实读取」，无法凭空补数据；此时 XPath 语义定位继续依赖 class chain + text + ivar 名。
6. **模拟器/真机差异**：图片渲染走主线程 `drawViewHierarchy`，真机 USB 隧道下大包传输耗时需在 P2-b 实测（官方口径 500 view 3–10s 指含图全量）。

## 验收标准建议

- resource-id：PackSmart 实弹抓取后，设置了 accessibilityIdentifier 的节点 XML 出现 resource-id；XPath `//*[@resource-id='...']` 命中；MCP `find_element` 可用 id 定位。
- 逐节点图片：深度抓取后画布图像模式呈现真实分层渲染；选中单节点图片加载 <1s；被测 App 全程不卡死（主线程让出可感知）。
- 3D：2D/3D 一键切换；拖拽旋转流畅（228 节点无掉帧）；3D 下点选节点与属性/树面板联动正确；重置回 2D 无残留。

## 明确不做

- 不做属性修改写路径（AttrModification，触发条件见记忆「路线 B 触发条件」）。
- 不做 WDA「任意 App」能力（二期独立立项，与 Lookin 自家 App 互补）。
- 不做全量带图自动抓取替代现有亚秒级快照——默认抓取保持「层级+属性+resource-id」，带图永远是显式动作。
