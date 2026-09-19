# VERSION

## 2026-09-17

- 重命名 skill：`layout-inspector` 改为 `layout-see`，定位收敛为 LayoutSee Core MCP 专属
- 数据源改为 LayoutSee Core MCP 12 工具（`capture_layout`、`get_layout`、`diagnose_layout` 等），移除 `.liv2` 与 uiautomator 离线解析、uiautodev 竞品链路
- 新增 `references/mcp-tools.md`（工具清单与 JSON-RPC 协议）、`references/mcp-direct-fallback.md`（MCP 未连接时脚本直连）、`scripts/mcp_call.py`（直连封装）
- 重写 `runtime-view-workflow.md`、`diagnosis-playbook.md`、`viewnode-schema.md`，对齐 LayoutSee 快照与节点 schema
- 删除 `parse_layout.py`、`liv2-format.md`、`uiautodev-mcp.md`、`uiautodev-browser-http.md`、`CHECK.md`

