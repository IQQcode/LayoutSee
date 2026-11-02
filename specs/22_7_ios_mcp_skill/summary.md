# iOS 布局抓取接入 MCP 与 Skill 总结

## 问题描述

iOS 布局抓取能力（`specs/22_7_ios_lookin/`）落地后，对外两个出口仍是 Android 专属：MCP 12 个内置工具中 3 个（get_device_info / get_current_app / get_screenshot）硬编码走 adb，iOS 设备调用会空转或报错；`skills/layout-see` skill 的触发条件、server 名、端点与平台语义全部只描述 Android，Agent 无法据此对 iOS 设备执行布局感知。

## 根因分析

功能类需求：iOS 链路（Lookin 协议驱动 + `_capture_ios`）产出的是与 Android 同构的快照 record，MCP 端点层（`/mcp/{deviceId}/sse|message`）也本就平台无关；缺口只集中在 `mcp_catalog.py` 三个 handler 直接调 `adb.*`、以及 skill 文档从未引入 iOS 语义。不是链路缺失，是分派层与知识层没跟上。

## 方案结论

- **MCP 对齐 HTTP 分支 + 快照回落**（用户确认）：三个工具的 iOS 行为与 server.py 既有 iOS HTTP 分支同口径——从最新快照读，无快照抛 `SNAPSHOT_STALE` / `LOOKIN_APP_NOT_FOUND` 引导先抓取；`get_screenshot` 实时调用回落最新快照底图。不自动抓取（读工具不带抓取副作用），不新建错误码。
- **单 skill 双平台**（用户确认）：不拆两个 skill——12 工具、七阶段工作流、诊断模板双端一致，差异收敛到 SKILL.md「平台差异」表（10 行）+ 各 references 的 iOS 注记。
- **写工具不新增逻辑**：iOS 恒只读在 `DeviceRegistry.is_readonly` 已生效，`_write_guarded` 天然拦截，只补单测验证。
- contracts 无需回填：`schemas/mcp/tool-catalog.json` 只约束工具结构，无平台字段。

## 已完成内容

- `mcp_catalog.py` 三个读工具 handler 按 `registry.device` 的 platform 分派：iOS 分支实现快照回落语义（device_info 返回 platform="ios"、density=null、orientation 按快照宽高推断、readonly=true；current_app 读快照 foreground；screenshot 回落快照底图）。
- `tests/test_ios_capture.py` 新增 `_mcp_call` 助手与 7 类 MCP 用例（iOS 读工具全字段/无快照错误码/写工具 READ_ONLY_MODE/Android 回归）。
- `skills/layout-see` 双平台化：SKILL.md（description 双端触发词、三形态 server 名、平台差异表、find_element 阈值语义）、mcp-tools.md（iOS 注记 + LOOKIN_APP_NOT_FOUND 错误码）、mcp-direct-fallback.md（device_id 三形态 + iOS 示例）、viewnode-schema.md（iOS 快照/节点示例 + extras 结构 + nodeKey 格式修正为层级路径）、runtime-view-workflow.md（定位证据双端化）、diagnosis-playbook.md（iOS 注记）、mcp_call.py（文案去 Android 中心化，行为零改动）、README/VERSION（双端定位）。
- skill 产物同步到用户级副本 `~/.agents/skills/layout-see/`（diff 为空）。

## 改动文件

- `repos/core/src/layoutsee_core/mcp_catalog.py`，三个读工具 iOS 平台分派（W1，commit e513633）
- `repos/core/tests/test_ios_capture.py`，MCP iOS 用例 + 测试基建 adb 替换（W1，同上）
- `skills/layout-see/SKILL.md`，双端触发词、数据源三形态、平台差异表、find_element 阈值语义（W2，commit daa63c9）
- `skills/layout-see/references/mcp-tools.md`，iOS 设备注记、错误码、tap ref 平台限定（W2）
- `skills/layout-see/references/mcp-direct-fallback.md`，device_id 三形态与 iOS 示例（W2）
- `skills/layout-see/references/viewnode-schema.md`，iOS 示例 + extras 结构 + nodeKey 格式修正（W2）
- `skills/layout-see/references/runtime-view-workflow.md`，定位证据与输出模板双端化（W2）
- `skills/layout-see/references/diagnosis-playbook.md`，iOS 注记（W2）
- `skills/layout-see/scripts/mcp_call.py`，docstring 与报错文案（W2，行为零变化）
- `skills/layout-see/README.md`、`skills/layout-see/VERSION.md`，双端定位与变更记录（W2）
- `~/.agents/skills/layout-see/`，用户级副本整目录同步（不参与 git）

## 验证结果

- [x] `npm run test:core` 全绿（180 tests，含 7 类新增 MCP iOS 用例；e513633 时点）
- [x] `npm run lint` 通过、`npm run contracts:check` 无漂移（e513633 时点）
- [x] `python3 -m py_compile skills/layout-see/scripts/mcp_call.py` 通过
- [x] 全目录无「仅 Android / 不用于 iOS」残留（grep 为空）
- [x] `diff -r -x '__pycache__' skills/layout-see ~/.agents/skills/layout-see` 为空（终审修复后复验）
- [x] W1 双 review：规格符合性 PASS、代码质量 PASS_WITH_NITS（全部 P3，无必须修复项）
- [x] W2 双 review：规格符合性 PASS（M1 修复）、代码质量两轮 FAIL→终审 PASS（find_element 检索阈值语义、归一化示例数字、「层级精度」伪差异行均按代码证据修正）
- [ ] 真机/模拟器 MCP 实调抽查（`mcp_call.py --devices` / `capture_layout` 对 iOS 设备）：留给用户可视化确认

## 后续建议

1. 用户在有 iOS 模拟器/真机的环境做一次实调抽查（读工具各调一次 + 确认写工具返回 READ_ONLY_MODE），作为最终可视化验收。
2. `finder.py` 的 iOS 命中面（仅 text 过阈值）可考虑后续让 find_element 支持 extras.ivar 匹配——skill 已按现状表述，若实现改进需同步 SKILL.md:53 与 mcp-tools.md。
3. server.py `_ios_window_size` / `_ios_foreground` 与 mcp_catalog.py 的 iOS 快照读取存在跨层同构（W1 review 备忘）：第 4 个 iOS 读工具出现时收敛为共享 helper。
4. 本会话工作期间检测到并行会话在 `repos/core`（`specs/22_7_ios_log_capture/`）开发 iOS 日志抓取，其改动未纳入本 story 两个提交，合并时注意分支状态。

## 适用边界

- 本结论基于当前 Lookin 协议能力：iOS 恒只读、无 density、synchronization 恒 best_effort、extras 采集 600 节点上限、hierarchyAccuracy 双端运行时均为 best_effort/limited（exact 仅契约枚举）。任一项能力演进（如 Lookin 支持注入）时，SKILL.md 平台差异表与 mcp-tools.md iOS 注记需同步更新。
- skill 的 iOS 表述以 commit daa63c9 + e513633 的 Core 行为为事实源；Core 后续改动若触及这三个工具或抓取链路，先跑 `tests/test_ios_capture.py` 再对照 skill 文档。
