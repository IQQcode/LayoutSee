# LayoutSee 布局查看 Skill

面向 AI Agent 的 Android 运行时视图感知工具。通过 LayoutSee Core MCP 读取真机 View 树，输出结构化控件树、精确坐标（boundsPx）和真实父子层级（parentKey），并内置六类布局诊断。

## 概览

当 AI 需要理解 Android 页面"屏幕上放了什么、放在哪里、多大、能不能点"时，本 skill 提供 View 树级别的结构证据，而不是靠截图猜测。数据全部来自 LayoutSee Core MCP，与桌面应用同源。

核心价值：

- `capture_layout` 原子抓取加 `get_layout` 取完整节点树，parentKey 给出精确层级
- `diagnose_layout` 内置六类异常诊断（重叠、遮挡、越界、点击区域过小、文本截断、不可见可交互）
- `find_element` 与 `query_xpath` 精确定位，`tap`、`swipe`、`input_text` 可控操作
- MCP 未连接时脚本直连本地端点，能力不打折

能力边界：

- 能回答：某控件的 boundsPx 是多少、父容器是谁、有没有兄弟节点覆盖它、点击区域是否正常
- 视觉类问题（文字为何显示不全）需结合 `get_screenshot` 与源码，标为推断
- 不支持静态 layout XML 源码阅读和 iOS 视图调试

## 快速上手

优先用会话内已连的 `layoutsee-android-<serial>` MCP，直接调工具：

```text
capture_layout()             抓当前页面，拿 snapshotId
get_layout()                 取完整节点树
diagnose_layout()            六类异常诊断
find_element(query="发布")    定位控件拿 ref
```

MCP 未连接时走脚本直连：

```bash
python3 scripts/mcp_call.py --list
python3 scripts/mcp_call.py capture_layout
python3 scripts/mcp_call.py get_layout --args '{"snapshotId":"<id>"}'
```

## 环境依赖

- LayoutSee 桌面应用已打开并连上 Android 真机（Core 默认 `127.0.0.1:11663`）。
- 直连脚本 `scripts/mcp_call.py` 只依赖 Python 3 标准库。

## 文档

- 工作流程与输出规范：`SKILL.md`
- MCP 工具清单与协议：`references/mcp-tools.md`
- 直连兜底：`references/mcp-direct-fallback.md`
- 七阶段工作流：`references/runtime-view-workflow.md`
- 诊断模板：`references/diagnosis-playbook.md`
- 快照与节点 schema：`references/viewnode-schema.md`
