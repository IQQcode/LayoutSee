# 22.8 Agent 能力展示：实施总结

设计：同目录 `doc.md`（2026-11-04）。

## 交付

按 doc.md 交付物表全部落地。文案、组件、样式与测试与设计一致。

## 验证结果

1. **单测/lint 全绿**：web 20 测（含 `agent-intro.test.mjs` 两条：判定函数七种组合、数据形状）、core `test_agent_intro_seen_boolean_key`、contracts 7 项、mac 握手；`npm run lint` 四段全过，版本门禁 22.7.0 不受影响。
2. **dev:web + 浏览器自检**（`LAYOUTSEE_DATA_DIR=/tmp` 隔离，不污染真实 settings）：
   - 首启弹窗在 `/devices` 与全局路由弹出，深色渲染正常（Sparkles lead + 三个 skill 行 + 知道了）。
   - 点击「知道了」后弹窗关闭；刷新不再弹；临时 settings.json 出现 `"agentIntroSeen": true`（PUT 链路验证）。
   - 设置页子导航出现「Agent」（设备与驱动之后）；分区四张卡渲染正确：头卡 chips 显示 `本地内核已连接 · 11663` 与 `MCP 工具 13 个`（动态计数 = 12 内置 + snapshot-overview 插件声明式工具，故文案用「MCP 工具」而非「内置」）；三张 Skill 卡的示例提示词复制框可用；深/浅两主题截图确认。
3. **图标**：`Bot/ScanEye/Wrench` 在打包 lucide 版本中存在（node import 校验），连同复用的 `Sparkles/Smartphone` 共五个 glyph。
4. **设置子导航 FOLO 化（用户追加）**：六行改为「icon + 文字」（Palette/Usb/Bot/Cast/ShieldCheck/Info，均 Lucide 描边集且 node import 校验存在）；图标恒用品牌色（`.settings-nav-icon`），激活态文字走既有 `.active` 样式；深浅两主题截图确认。

## 过程修正

- 切片测试首跑把 `export` 关键字带进 `new Function` 报语法错——改为从 `function shouldShowIntro` 起切（仓库既有做法）。
- 自检时 IAB 自动化对弹窗按钮的 Playwright actionability 等待超时（`elementFromPoint` 证实命中点无遮挡），属自动化环境怪癖而非产品缺陷：改用页面侧 `click()` 完成验证，真人点击不受影响。

## 遗留与人工事项

- **可视化验收**（人负责）：DMG 形态下的弹窗观感与时机（壳宿主会话就绪后弹出）由用户最终确认。
- git 提交未做（主 session 受 Mimosa 基线拦截，按惯例走子代理或用户执行）。
- 弹窗 lead 的「12 个工具」为契约固定值（内置工具），与设置页动态计数（含插件贡献）口径不同，属有意区分。
