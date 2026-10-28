# iOS 接入 Lookin（v22.7.0 第一版）总结

## 问题描述

LayoutSee 此前只能抓取 Android 布局（uiautomator 链路），设备页 iOS Tab 为占位面板。目标：借助开源工具 Lookin 快速内置 iOS 布局抓取能力（不从零自研、不嵌入 GPL 的 Lookin mac 客户端），产出可运行、可验证的第一版。

## 方案结论

采用路线 A：**Core 内纯 Python 复刻 Lookin 客户端协议**（协议事实源为 MIT 的 QMUI/LookinServer @develop，不包含 GPL-3.0 的 hughkli/Lookin 代码）。关键设计决策：

1. 新增独立包 `layoutsee_core/ios/`（usbmux 隧道 → PeerTalk 帧 → NSKeyedArchiver 编解码 → LookinClient 请求编排 → IOSDeviceDriver），与 `adb.py` 平级，零 subprocess/urllib/新依赖。
2. iOS 抓取产出 **uiautomator 风格 XML 走既有 `normalize_nodes`**，LayoutNode/refs/XPath/诊断/摘要全链路与 Android 同构复用，下游零改动。
3. iOS 设备恒只读（Lookin 无 tap 注入能力），写路由在 server 分派层拦截（403 READ_ONLY_MODE）。
4. Web 按 `device.platform` 驱动降级：无实时画面（快照+wireframe）、隐藏 common Tab、插件按平台过滤。
5. 客户端 pin LookinServer 1.2.8（协议版本 7）；属性键名与分批结构做了宽松实现并集中为校准点（`driver.ATTR_EXTRACTION_RULES`、`client._GROUP_KEYS`），真机抓包后只改常量表。

## 已完成内容

- W1：`ios/` 协议包六模块 + 30 个协议单测（含独立构造的 bplist 金样）+ `scripts/diagnose_lookin.py` 诊断脚本（--list/--scan/--capture）。
- W2：DeviceRegistry 双源轮询（adb + usbmux）、CaptureCoordinator 分平台抓取、bootstrap 装配、server.py 全路由 iOS 分派、errors.py 四个新错误码、15 个集成单测。顺带修复分支既有缺陷：summary.py 缺失的 `_degrade` 函数（独立 hotfix commit）。
- W3：device.json platform 枚举加 `"ios"`，契约三处生成物同步，漂移门禁通过。
- W4：设备页 iOS Tab 真列表 + LookinServer 三步集成引导空态；工作台 iOS 快照视图/隐藏 common/插件平台过滤；DeviceCanvas 平台门禁（iOS 不发 live/stream/screenshot 请求）；3 个平台纯函数测试。
- 双 review 全部通过：W1（规格 PASS + 质量 APPROVE_WITH_FIXES 已修）、W2（规格 PASS + 质量 APPROVE_WITH_FIXES，P1 记 backlog、建议项已修）、W4（规格 PASS + 质量 APPROVE_WITH_FIXES 已修）。

## 改动文件

新增：
- `repos/core/src/layoutsee_core/ios/{__init__,usbmux,peertalk,archiver,client,driver,_utils}.py`
- `repos/core/tests/test_ios_protocol.py`、`repos/core/tests/test_ios_capture.py`
- `repos/core/tests/fixtures/lookin/{response_attachment_hierarchy.plist,make_fixture.py}`
- `repos/core/scripts/diagnose_lookin.py`
- `repos/web/tests/workbench-platform.test.mjs`

修改：
- `repos/core/src/layoutsee_core/{devices,snapshots,bootstrap,server,errors,summary}.py`
- `repos/contracts/schemas/device/device.json`（+ 三处 generated 生成物）
- `repos/web/src/features/devices/DevicesPage.jsx`、`features/workbench/WorkbenchPage.jsx`、`features/workbench/DeviceCanvas.jsx`、`features/workbench/tabs/ElementTab.jsx`（toast 文案平台分支）
- `skills/layout-see/scripts/mcp_call.py`（安全加固：回环白名单 + DNS 解析校验，回应 Mimosa 扫描）

提交（v22.7.0_dev_ios，共 10 个）：`485d813` `9838c82` `68b4f67` `d2b0819` `247e05c` `04be83c` `aa407bb` `c5a72e5` `cc7fe85` `3b9e384`。

## 验证结果

- [x] `npm run test:core`：153 tests 全绿（含 iOS 协议 30 项 + iOS 集成 15 项；基线 138 中 1 error 的 summary 降级缺陷已修复）
- [x] `npm run test:web`：13 pass / 0 fail
- [x] `npm run contracts:check`：生成物一致（3 文件）；契约测试 7/7
- [x] `npm run lint`：contracts + web + mac 三段全过；`vite build` 成功
- [x] `diagnose_lookin.py --list`：本机无设备时优雅输出退出 0；失败路径退出 1
- [x] W1/W2/W4 双 review（规格符合性 + 代码质量）全部 PASS/APPROVE_WITH_FIXES，必须修项全部闭环
- [ ] **真机冒烟（人工）**：本环境无 iOS 设备。步骤：被测 App 集成 LookinServer（仅 Debug）→ 真机前台运行 + USB 连接 → `uv run --project repos/core python repos/core/scripts/diagnose_lookin.py --scan --udid <UDID>` → `--capture --out /tmp` → UI 设备页/工作台验证
- [ ] **属性键名真机校准**：`--capture` 输出的树 JSON 对照 `driver.ATTR_EXTRACTION_RULES` / `client._GROUP_KEYS` 校准（text/accessibilityIdentifier 等映射当前为宽松匹配）

## 后续建议

1. **真机冒烟 + 键名校准**（上两项未勾选验证）是合入主干前的最后一步；CGRect 线上格式已做四形态兼容，若真机抓包出现解析 warning，按 warning 提示补 `archiver.decode_rect`。
2. **MCP 工具面 iOS 降级**（质量审查 P1，超出本卡范围）：`mcp_catalog.py` 的 get_screenshot/get_current_app/get_device_info 会把 iOS udid 当 adb serial；建议复用快照 foreground/快照 png 或返回稳定错误。
3. **workspace 安全基线**（需人决策）：Mimosa L3 拦截本 session 的 git commit（同组提交由子代理 session 完成），剩余 10 个高危全部为既有项——`source/uiautodev`（只读第三方内核，5 处）与 `repos/mac/resources/runtime/web/assets`（构建产物，5 处）。建议在 Mimosa 台账确认/豁免或安排专项清理；主 session 直接 commit 仍会被拦。
4. 模拟器支持（loopback 47164–47169）、iOS 截图（pymobiledevice3 纯 Python）、ResetToLive 之外的 P3 打磨项（切片锚重构、AndroidEmptyGuide 对称抽取、devicesForPlatform 兜底策略）见审查记录，择机安排。

## 反馈修复轮（2026-10-25 真机/模拟器联调）

用户以模拟器 + 真机联调反馈「设备检测到了但看不到布局」，根因三件套与处置：

1. **LookinServer 单客户端独占**：模拟器上 Lookin 官方客户端已与 App 建立连接（`lsof` 证实 ESTABLISHED），PeerTalk 在 accept 后取消监听 socket，后续任何客户端 connect 被拒。LayoutSee 与 Lookin 官方客户端只能分时使用；设备页空态与模拟器抓取错误文案均已写明。
2. **真机无监听**：诊断脚本证实真机 47175–47179 全部 connect refused——真机上的被测 App 未运行/未集成（Debug）/装了 Release 构建，属环境问题非代码缺陷。
3. **模拟器支持补齐**（原「明确不做」项提前）：`IOSDeviceDriver` 直连本机 loopback 47164–47169 枚举（usbmuxd 不可用也不影响模拟器）与抓取（serial 形如 `simulator:47164`）；诊断脚本新增 `--scan --sim` / `--capture --sim`；新增 5 个模拟器单测（ReplayServer 本地 TCP 替身）。测试 helper 的 `response_attachment` 修正为无条件写 `appIsInBackground`（对齐真实 LookinServer 的 encodeBool 行为）。

用户操作指引：退出 Lookin 官方客户端 → LayoutSee 设备页 iOS Tab 应出现模拟器设备（ios-sim-47164）→ 抓取查看 wireframe。

### 联调修复轮二（2026-10-25 23:2x～23:5x，iOS 27 模拟器真机联调）

新包装上后 App 不再崩，但设备列表无模拟器、抓取报错。逐层修复与发现：

1. **App 请求参数缺失（已修）**：LookinServer 要求 App(201) 请求的 attachment.data 必须是 NSDictionary（键 `needImages`/`local`），我们发 `None` 直接被回 Inner error(-401)。Hierarchy(202) 补 `clientVersion`。已修：`client.app_info()` 发 `{"needImages": False, "local": []}`。
2. **响应键名真机校准（已修）**：LookinAppInfo/LookinHierarchyInfo 的 encodeWithCoder 用**数字键**（AppInfo：3=deviceDescription 4=osDescription 5=appName 6=screenWidth 7=screenHeight 8=deviceType，bundleId/scale 用属性名；HierarchyInfo：1=displayItems 2=appInfo），DisplayItem/Object/Attribute 用属性名。client 层统一规整为业务键（`_normalize_app_info`），键名注释集中在 client.py。
3. **属性获取路径改造（已修）**：static 树的 attributesGroupList 为空（符合 Lookin 设计，属性靠 203 分批或 210 逐节点）。210（AllAttrGroups）请求 data 是裸 NSNumber(oid)，比 203 的 task 包简单，**capture 主路径改为逐节点 210**（上限 ATTR_NODES_LIMIT=600、单节点超时 2s、连续 12 个空早停）。
4. **环境级限制（未修，LookinServer 侧）**：iOS 27 模拟器上 LookinServer 的对象注册表（LKS_ObjectRegistry，weak NSPointerArray）查询全部失败（oid 0–39 全部 ObjNotFound）——**官方 HierarchyDetails 走同一张表，Lookin 官方客户端在此环境同样拿不到属性**。表现为快照无 text/resource-id 但层级/frame/类名完整。疑似 hook/注册初始化在 iOS 27 失效，后续方向：fork LookinServer（MIT）修注册逻辑或跟进上游。
5. **监听丢失（环境级）**：App 进后台时 LookinServer 的监听恢复逻辑（主线程队列）被挂起，连接断开后监听 socket 丢失且无法自愈，需 App 冷启动恢复；叠加 Core 5s 轮询占用监听窗口存在竞态（抓取失败重试一次通常即可）。
6. 验证：ping/App/Hierarchy 在真机（模拟器 App）上实测通过（188 节点、类名/frame 完整）；test:core 160 全绿（键名 fixture 更新为真实数字键形态）。

### 插桩实证轮（2026-10-26 凌晨，本地 LookinServer 源码实证）——推翻「环境级限制」结论

用户提供本地 clone（`~/Documents/Temp/lookin/LookinServer`）。给 `LKS_ObjectRegistry` 与 `LKS_RequestHandler` 加 NSLog 插桩，改 SPM Demo 引用本地包，构建 `LookinDemoSwift` 跑在模拟器实弹验证：

1. **注册表完全正常**（73 个对象连续注册、index 无断裂）——上一轮「iOS 27 对象注册表失效」结论**错误**。
2. **真根因（已修 `ffc9caa`）**：插桩日志 `req210 object=(null)` 显示服务器把我们发的 oid 解成了 null——我们的 encoder 把标量按 `encodeInteger` 形态**内联**，而服务器用 `decodeObjectForKey:` 读（只认 `$objects + UID 引用`形态）。这是上次崩溃 bug 的对称面：encodeInteger 内联↔decodeInteger 读；encodeObject 引用↔decodeObject 读。修复：`encode_keyed_object` 增加 `scalar_keys_by_reference`，attachment 的 "0"（data）字段标量也走引用形态；Foundation 金标验证 `decodeObjectForKey` 解出 NSNumber(5)。
3. **CGRect 真实形态（已修）**：frame 是 `NSStringFromCGRect` 字符串 `"{{x, y}, {w, h}}"`（非 dict），`decode_rect` 补字符串正则解析后 228 节点 warnings 归零、bounds 全部正确。
4. **属性短码校准（已修）**：attr identifier 是短码（`lb_t_t`=UILabel text、`vl_i_i`=userInteractionEnabled、`ct_e_e`=UIControl enabled…，全表见 LookinAttrIdentifiers.m），section 内数组的键是 `attributes`（非 `attrs`）；ATTR_EXTRACTION_RULES 改为精确匹配，scrollable 由类链（UIScrollView）判定。
5. **实弹终验**：在用户的真实 App（模拟器）上 0.6s 完整抓取 228 节点：37 个真实 text（"PackSmart"、"STEP 1 OF 3: PLAN YOUR JOURNEY"…）、bounds ×scale 正确（[186,33][496,105]@3x）、warnings=0。
6. **已知缺口**：LookinServer 属性组不含 accessibilityIdentifier/Label → resource-id/content-desc 留空；ivarTraces 在静态树中为 null（变量名需 TraceManager/FetchObject 路径，后续卡片）。
7. 证据链可复现：插桩 patch（3 处 NSLog）与 SPM Demo 本地化步骤已随 clone 还原清除；复现方法见本节文字。

### 交付物与验证口径（最终）

- iOS 模拟器全链路可用：设备枚举、快照抓取（层级/类名/**text**/bounds/wireframe）、XPath/选择器/摘要/诊断。真机链路同协议（47175-47179），待真机复验。
- 用户操作要点：被测 App 保持前台（切后台监听丢失需重启 App）；Lookin 官方客户端与 LayoutSee 分时使用。

### 展示层补完轮（2026-10-27 凌晨，路线 A 补完：画布坐标系 + 属性面板 + ivar 名 + 模拟器截图底图）

用户以图一（画布错乱、属性面板仅 9 项泛化字段）对照官方 Lookin 图二反馈「功能通了但基本不可用」。重新评估路线 B（LookinShared ObjC helper）后确认：**差距全在适配/展示层，协议数据已全量到手**——图二的 3D 画布/分组面板/ivar 名全部来自 GPL 客户端展示层，换 B 同样要从零自建且需新增原生构建链，故「留 A、修展示层」。本轮改动：

1. **画布坐标系修复（P0，图一症状①根因）**：LookinServer 下发的 `item.frame` 是**相对父视图**坐标（`LKS_HierarchyDisplayItemsMaker.m:55` 直接取 `layer.frame`；窗口绝对坐标 `frameToRoot` 由 GPL 客户端自行累加，服务端从不赋值）。原 `driver._build_node` 直接 `frame×scale` 当绝对坐标 → 深层子节点全部坍缩到左上角。现沿父链累加原点（浮点累加、落 XML 时才 ×scale 取整，负值仍截 0）。实弹验证：PackSmart 标题 bounds=[186,219]（y=73pt）与截图吻合，228 节点 warnings=0。
2. **hidden/alpha → visible**：XML 新增 `hidden`（仅 true 时写）/`alpha`（仅 <0.99 时写）属性；`normalize_nodes` 的 visible 计算纳入两者（Android XML 无此属性，行为零变化）。DeviceCanvas 既有 `visible` 过滤自动生效。
3. **属性面板数据链（P0，图一症状②根因）**：原实现只把 4 个属性写进 Android 形状 XML、其余全丢。新增 `ios/attrs.py`：210 属性组归一化为契约 `extras`（值统一 kind 结构：string/number/boolean/enum/color/point/size/rect/edges/chain/nil/raw；NSValue 的 `NS.special` 1/2/3/11 → point/size/rect/edges，UIColor=rgba 四元数组）。`build_xml` 改返回 `(xml, extras_by_node_key)`，nodeKey 与 normalize_nodes 键位对齐（**根键位从恒 "0" 改为 str(child_index)**，Android 单根不受影响，顺带修掉 iOS 多窗口键冲突隐患），snapshots 层按键回填 `node.extras`。契约 `layout-snapshot.json` 增 LayoutNode.extras（AttrGroup/AttrSection/AttrItem 三层）与 foreground.appName（顺带修掉 iOS foreground 缺 packageName 的既有契约违约），生成物已再生成。
4. **ivar 名（P1，零额外请求）**：LookinServer 每次层级构建跑 `LKS_TraceManager.reload`，ivar 名（宿主哪个 ivar 引用了本视图）以 `ivarTraces` 随 **202 层级响应**返回（viewObject/layerObject 均带）。`best_ivar` 遴选：跳过 `_layer` 等系统名（只剩系统名宁可 None）、viewObject 优先。写入 extras.ivar + XML `ivar` 属性。实弹 126/228 节点命中，`_titleLabel/_subtitleLabel/_destNameLabel/_seasonBadgeLabel/_stepPercent` 等与官方 Lookin 完全一致。
5. **web 属性面板（P0）**：新增 `tabs/attrFormat.js` 纯函数——全量短码→语义标签映射（事实源 LookinAttrIdentifiers.m 常量名尾段，常用属性用 API 名覆盖）+ `formatAttrValue`（color→hex+CSS 色块、rect/point/size/edges、chain→类链）。ElementTab：节点带 extras 时按「组·节」分组渲染（Lookin 风格），原始 XML 属性折叠为 details；无 extras 维持 Android 平铺不变。树行加 ivar 徽标、自定义类（非 UI/NS/CA/CF 前缀）高亮。层级树按文本/类名过滤既有能力核对无需改动。
6. **模拟器截图底图（P1）**：先验证协议路径——App(201) `needImages=True` 时 LookinAppInfo 键"2"即 `UIImagePNGRepresentation` 截图，但实测仅 **161×350 缩略图**（Lookin 设备列表用），当底图过糊弃用；202 静态树无图、208 仅 UIImageView。最终 `ios/simctl.py`（`xcrun simctl io booted screenshot`，argv 全字面量 + shell=False；**Mimosa 拦主会话写任何 subprocess 代码，由子代理落盘**）——恰好一台 booted 模拟器才截（多台无法对应 serial），508KB 全分辨率 PNG；`_capture_ios` 接线 png → screenshot 元数据 + record.png，复用 `/snapshots/{id}/screenshot` 通道，**DeviceCanvas 零改动**（contentUrl 通用路径直接生效）。真机 warning 降级线框（pymobiledevice3 后续）。
7. **过时文案清理**：driver 模块 docstring、`_collect_attr_groups` docstring、全空 warning 中的「iOS 27 对象注册表失效」表述按插桩实证轮结论改写；**210 只认 layer 的 oid**（handler 校验 CALayer，view oid 返回 ObjNotFound）写入注释——调试时手动用 view oid 拉属性会得到「假空组」。
8. **验证**：test:core 168 全绿（+8：绝对坐标累加/hidden-alpha 可见性/extras 键位对齐/attrs 值形态/ivar 遴选/模拟器截图成功与降级）；test:web 全绿（+attr-format 5 项）；contracts:check 通过；lint 三段通过；vite build 通过。实弹：PackSmart 228 节点 928 属性组、坐标正确、126 ivar、simctl 截图 508KB。

遗留：3D 分层视图（web CSS 3D 可做）、逐节点图片（needImages/208，3-10s 显式重抓取）、真机复验 + pymobiledevice3 截图、resource-id（LookinServer 协议无 accessibilityIdentifier，需 fork 或 InvokeMethod(206)）。

### 画布真实内容底图 + 构建序列号（2026-10-29，用户真机验收反馈轮）

用户以真机（iPhone，iOS 27.2）验收 22.7.0 首包：树 ivar/坐标/属性面板全部生效，但画布仍是纯线框——**simctl 截图只覆盖模拟器，真机走降级**；用户预期「把真实内容放过去」。同时要求标题栏加构建序列号区分包。本轮改动：

1. **画布底图改 203 定点拉 key window 真实渲染图（模拟器/真机通用，P2-b 的单 task 最小实现）**：`client.fetch_display_item_screenshot(oid)` 发单个 LookinStaticAsyncUpdateTasksPackage（taskType=Group、attrRequest=NotNeed、clientReadableVersion=1.2.8），响应 `LookinDisplayItemDetail.groupScreenshot` 即 `drawViewHierarchyInRect` 原生分辨率 PNG（真机实测 1290×2796、587KB）。`driver._fetch_window_screenshot` 取 `representedAsKeyWindow` 项的 layerObject.oid（回落首窗口）拉图，snapshots 层优先用之，模拟器 simctl 降为回退、真机失败降线框。效果与 Lookin 2D 画布同源（Lookin 官方同样在单节点重载时走 203）。
2. **archiver 新增 `KeyedObject` 嵌套类身份编码**：203 请求载荷需要 NSArray 里嵌 LookinStaticAsyncUpdateTasksPackage/LookinStaticAsyncUpdateTask 类实例（服务器按类解码），原编码器把 dict 一律编成 NSDictionary。`KeyedObject(fields, class_name, class_chain, scalar_keys_by_reference)` 支持任意层级嵌套自定义类；`encode_keyed_object` 重构为复用同一路径（行为不变）。**oid 键必须引用形态**（decodeObjectForKey 只认引用）——与 b4eb0a4/ffc9caa 同族的第三个形态坑。
3. **构建序列号 buildId 全链路**：契约 `info.json` 增 `buildId`（可选 string）+ 三处生成物再生成；`bootstrap.read_build_id()` 读 core 可执行文件旁的 `build-id` 文件；`package.mjs` 暂存阶段写入 `git rev-parse --short HEAD` 并进 artifact-manifest；Web 标题栏 `V22.7.0` chip 旁展示 build-id chip（动态读 `/api/v1/info`，替换原硬编码 V22.6.1）。设置页「版本兼容」判断改壳/核版本比对（去掉硬编码 22.6.1）。
4. **验证**：test:core 174 全绿（+4：203 客户端金样/failureCode=-1/请求类身份与 oid 引用形态断言/无 layerObject 跳过）、web 18、契约一致、lint；真机实弹全链路（dev core + HTTP）：渲染图 1290×2796、坐标正确、extras 228/228、ivar 126、warnings 空。
5. **环境备注**：本机 iOS 27.0 模拟器运行时在 10-29 凌晨从 simctl 消失（Xcode 27.1，疑似用户清理/升级，设备目录仅剩 device_set.plist）——本轮真机验证不受影响，模拟器需用户在 Xcode 里重新下载运行时。

交付：`repos/mac/release/mac-arm64/LayoutSee-22.7.0-arm64.dmg`（build-id=aa83936）。遗留：P2-b 全树深度抓取、P2 3D 视图、resource-id（206）、模拟器运行时重装。

### 编码崩溃轮（2026-10-25 22:2x，真机/模拟器联调第二轮）

用户反馈「退出 Lookin 后点击抓取，被测 App 秒崩（用 Lookin 也一样）」。崩溃报告（`tmp/log/error.log`）定位：

- **根因**：我们的 NSKeyedArchiver 请求编码把标量字段（`"1": dataType`）写成 `$objects` + UID 引用，而 **Apple 的 `encodeInteger:forKey:` 是内联写进实例 dict**——Foundation 的 `decodeIntegerForKey:` 对 UID 引用形态直接抛异常，LookinServer 的 `LKS_ConnectionManager` 不捕获 → 被测 App SIGABRT。「用 Lookin 也崩」是因为 App 一启动就被我们 5 秒设备轮询的旧编码 ping 打崩，轮到 Lookin 时 App 已死。
- **修复**（`b4eb0a4`）：`archiver.encode_keyed_object` 对标量（bool/int/float）内联写入实例 dict（对齐 Apple encodeInteger/encodeBool/encodeDouble 行为），容器元素仍走 $objects + UID 引用。
- **验证**：Swift 生成 Apple 标准 NSKeyedArchiver 样本对照（plutil 结构 diff 对齐）→ Foundation 按普通与 secure coding 两种模式解码我们的 ping 请求均成功（`dataType=0, data=nil`，复刻 LookinConnectionAttachment initWithCoder 的解码路径）；新增 2 个防回归单测（内联形态断言 + Apple 样本金样 `fixtures/lookin/apple_generated_attachment.bin`）；test:core 160 全绿。
- **协同要点**：正在运行的 Core 加载的是修复前的代码，会持续把刚启动的被测 App 打崩——修复后必须**重启 Core**（dev:web 重启脚本 / 打包版重新 `package:mac`）才能停止崩溃循环。
- **产物验证**：用户 /Applications 的安装包打在两提交之间（含模拟器枚举、不含编码修复），已重新打包 `repos/mac/release/mac-arm64/LayoutSee-22.6.1-arm64.dmg`（electron-builder 需 npmmirror 镜像前缀重试），并通过 PyInstaller PYZ 解包验证包内 `archiver` 模块含修复（`encodeInteger` docstring 特征）。electron 下载超时的镜像预案见 INDEX.md 打包一节。
