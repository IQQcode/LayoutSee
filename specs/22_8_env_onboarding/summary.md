# 22.8 一键环境配置：实施总结

设计：同目录 `doc.md`（2026-11-03）。Story 索引：`docs/STORY.md`。

## 交付

| 交付物 | 内容 |
| --- | --- |
| `skills/layout-env/` | SKILL.md（触发词 + 体检→修复→复检流程）、`scripts/env_check.py`（`check [--json]` 七项体检 / `set-adb` 写 adbPath，exit 0/1/2/3，`LAYOUTSEE_DATA_DIR` 可演练）、references 的 android-setup / ios-setup |
| `skills/layout-lookin-server/` | SKILL.md（摸底→选路径→改文件→构建验证→验收）、`scripts/inspect_ios_project.py`（只读摸底，verdict 七态）、references 的 cocoapods / spm（pbxproj 五段结构）/ troubleshooting |
| 根 README.md / README.en.md | 修正过时 iOS 表述（原「iOS 与 HarmonyOS 仍为界面预览」）、补 LookinServer 前置说明、「交给 Agent」补两个 skill 与示例 prompt |
| `docs/repo-structure.md` / `docs/STORY.md` / `docs/story/26-11-03-一键环境配置skill.md` | 结构树、导航、Story 索引与拆解落盘 |

两个 skill 均已 rsync 到 `~/.agents/skills/`（排除 `__pycache__`，diff 一致）——用户级副本是全局会话实际加载版。

## 验证结果（非可视化）

1. **env_check.py 真跑**（本机）：LayoutSee.app 已装、Core 未运行、adb 命中 settings 指定路径（version 1.0.41）、Xcode 27.2 + 4 个 iOS runtime、CocoaPods 缺失提示、Lookin 未运行；JSON 与人读报告字段一致，exit 1（有缺口）。
2. **set-adb 演练**（`LAYOUTSEE_DATA_DIR=/tmp`）：非法路径 exit 3；合法写入 exit 0，保留其余键、0600、tmp+replace 原子写；App 运行拒写分支由 pgrep 守卫（本机 Core 未运行，未实际触发 refused）。
3. **inspect_ios_project.py fixture**：CocoaPods 已集成（lock 版本 1.1.9 → 建议升 1.2.8）、SPM 已集成（minimumVersion 1.2.8 提取）、空目录 unknown，三态正确。
4. **静态检查**：两脚本 `py_compile` 通过；skill 全部相对链接可达（自检脚本）；`npm run lint` 全绿（version:check 22.7.0 门禁未受影响）。
5. **零产品代码改动**：`repos/` 五个模块未触碰。

## 过程修正

- `check_adb` 候选路径遍历 tuple 解包 bug（首跑即暴露，已修）。
- `Podfile.lock` 版本行带 `- ` 前缀导致 regex 不匹配（fixture 暴露，已修）。

## 遗留与人工事项

- **可视化/真机验收**（人负责）：LayoutSee 设备列表出现 `ios-*` 设备需真实 Debug App；建议拿任一自己的 iOS 工程跑一遍 `layout-lookin-server` 全流程。
- git 提交未做：主 session 的 commit/push 受 Mimosa 全仓基线拦截，按惯例由子代理或用户执行（提交前 `git ls-files` 核实未追踪文件）。
- npm 包方案已否决（用户确认 skill-only）；若未来发布，可把 `env_check.py` 的检查矩阵移植为 Node CLI 并在设备页空态挂 `npx` 提示。
