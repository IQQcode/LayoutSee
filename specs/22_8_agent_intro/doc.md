# 22.8 Agent 能力展示：首启弹窗 + 设置 Agent 分区 设计

状态：实施完成（summary 见同目录 `summary.md`）。

## 背景与目标

LayoutSee 的 Agent 能力（MCP 12 内置工具 + 三个随包 Skill）只写在 README，装完应用的用户无感知。目标：

1. **首次安装打开后弹窗**提示 Agent 能力（仅首次展示）。
2. **设置页新增「Agent」分区**（参考 FOLO 设置样式：卡片 + 状态 chips + 可复制提示词框）。

## 关键决策

- **持久化用 Core settings 键 `agentIntroSeen`**（DEFAULTS + UPDATABLE_KEYS 各一行）：这是唯一跨端口漂移（11663-11672）与跨宿主（shell/browser）共享的存储；localStorage 只能按 `127.0.0.1:<port>` origin 隔离，作兜底标记（`layoutsee.agentIntroSeen`）防写失败重弹。
- **contracts 零改动**：`/api/v1/settings` GET/PUT 是泛型 envelope，无 settings schema/fixture。
- **弹窗挂载点**：`main.jsx` `ToastProvider` 内、`Routes` 旁——覆盖 WorkbenchPage 独立路由；会话判定走 `HostBridge.subscribe`（KernelBanner 范式），`no_session` 只读观察模式不弹。
- **升级老用户会看到一次**（settings 无该键视为未看过）：作为能力公告接受。
- 图标走既有 `MorphIcons.jsx` 约定（Lucide 描边数据、构建期打包）：新增 `bot`/`scanEye`/`wrench`/`sparkles`/`smartphone` 五个 glyph。

## 文案（用户草稿润色定稿）

- 弹窗标题：让 AI 读懂你的界面
- lead：LayoutSee 把设备运行时视图树交给 AI——控件是什么、在哪、多大、能不能点，都有结构依据。MCP 已内置 12 个工具（9 读 3 写），随设备开箱即用。
- 三个 Skill（名称 + tag + 一句话）：layout-see·布局感知 / layout-env·一键配置 / layout-lookin-server·iOS 接入；尾注引导「详情见 设置 → Agent」。
- 设置 Agent 分区：头卡（Bot 图标 + 描述 + chips「本地内核已连接 · port」「MCP 工具 N 个」（`api.mcpTools()` 动态计数，含插件贡献，故不写死"内置"））→ 三张 Skill 卡（图标 + 名 + tag + 描述 + 可复制示例提示词）→ MCP 端点指引卡。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `repos/core/src/layoutsee_core/settings.py` | `agentIntroSeen` 键（DEFAULTS/UPDATABLE_KEYS） |
| `repos/core/tests/test_diagnostics_settings.py` | 布尔键单测 |
| `repos/web/src/features/onboarding/agentSkills.js` | 弹窗/分区共用文案数据（纯 ESM，可直测） |
| `repos/web/src/features/onboarding/AgentIntroDialog.jsx` | 首启弹窗；`shouldShowIntro` 纯函数 |
| `repos/web/src/main.jsx` | Routes 旁挂载 |
| `repos/web/src/features/settings/SettingsPage.jsx` | `SECTIONS` 加 agent + 四张卡 + `mcpTools` 拉取 |
| `repos/web/src/components/MorphIcons.jsx` | 五个新 glyph |
| `repos/web/src/styles/app.css` | `.agent-skill-head`/`.skill-tag`/`.prompt-box`/`.intro-*` 样式 |
| `repos/web/tests/agent-intro.test.mjs` | 判定函数切片测试 + 数据形状测试 |

## 验收标准

1. `npm run test:unit` + `lint` 全绿（含新增用例）。
2. dev:web 自检：弹窗内容正确、关闭后不再弹（settings + localStorage 双标记）、设置 Agent 分区卡片/复制框/chips 正常、深浅两主题适配。
