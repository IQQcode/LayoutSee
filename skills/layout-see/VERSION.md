# VERSION

## 2026-11-01

- skill 双平台化：新增 iOS 支持（Lookin 链路，iOS 真机/模拟器均可抓取），此前为 Android 单端
- SKILL.md 触发词与数据源补双端三形态 server 名（`layoutsee-android-<serial>` / `layoutsee-ios-<udid>` / `layoutsee-ios-sim-<port>`），新增「平台差异」节（iOS 恒只读、无 density、bundleId、ObjC 类名、extras/ivar、底图降级、单客户端独占、后台丢监听）
- `mcp-tools.md` 补 iOS 设备注记与 `LOOKIN_APP_NOT_FOUND` 错误码；`mcp-direct-fallback.md` device_id 三形态与 iOS 示例；`viewnode-schema.md` 补 iOS 快照示例；`runtime-view-workflow.md` resource-id 措辞双端化；`mcp_call.py` 报错文案去 Android 中心化
- README 定位改双端

## 2026-09-17

- 重命名 skill：`layout-inspector` 改为 `layout-see`，定位收敛为 LayoutSee Core MCP 专属
- 数据源改为 LayoutSee Core MCP 12 工具（`capture_layout`、`get_layout`、`diagnose_layout` 等），移除 `.liv2` 与 uiautomator 离线解析、uiautodev 竞品链路
- 新增 `references/mcp-tools.md`（工具清单与 JSON-RPC 协议）、`references/mcp-direct-fallback.md`（MCP 未连接时脚本直连）、`scripts/mcp_call.py`（直连封装）
- 重写 `runtime-view-workflow.md`、`diagnosis-playbook.md`、`viewnode-schema.md`，对齐 LayoutSee 快照与节点 schema
- 删除 `parse_layout.py`、`liv2-format.md`、`uiautodev-mcp.md`、`uiautodev-browser-http.md`、`CHECK.md`

