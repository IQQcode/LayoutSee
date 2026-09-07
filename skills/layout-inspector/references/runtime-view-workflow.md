# Android 运行时视图感知工作流

## 核心原则

1. 运行时 View 树是结构证据，截图是视觉证据。
2. class、resource-id、bounds、父子关系和交互属性必须来自结构源。
3. OCR、图标语义和业务含义属于补充或推断，不能冒充结构事实。
4. 修复前后使用同一采集源、同一页面状态和同一目标节点进行比较。

## 证据优先级

1. `.liv2` 结构化解析：原生属性可信度高，父子层级由 `meta:__child__N` 恢复；坐标仍需考虑 scale、matrix 和窗口 inset 限制。
2. `.liv2` 固定 key 兜底：坐标和 resource-id 可用于定位，父子层级为近似推断。
3. uiautomator XML：层级、text、content-desc 和交互属性完整，但可能缺少自绘与 WebView 内容。
4. Uiautodev Desktop MCP：实时返回 uiautomator XML，并提供设备上下文。
5. uiautodev 浏览器 HTTP：实时返回 JSON 或 XML hierarchy，适合在线读取和交叉验证。
6. screen-oracle、fast-brain、截图：用于视觉与语义补充。

## 七阶段流程

### 1. 采集

记录：

- `sourceType`
- 采集时间
- 设备 serial 和型号
- package 和 Activity
- 屏幕尺寸
- 页面标题或关键文本
- 原始文件或接口来源

实时采集时，currentApp 与 hierarchy 必须属于同一批次。若页面跳转，丢弃本批结果并重采。

### 2. 标准化

统一：

- `bounds = [left, top, right, bottom]`
- `width = right - left`
- `height = bottom - top`
- `center = [(left + right) / 2, (top + bottom) / 2]`
- 空 resource-id、text、content-desc 归一化为空值
- 布尔属性使用 true 或 false

`.liv2` 的 `v2-structured` 结果标注为 `exact_v2`，`legacy-key-scan` 结果标注为 `approximate`，uiautomator XML 层级标注为 `exact_xml`。

### 3. 查询

可按以下属性定位节点：

- resource-id
- class
- text
- content-desc
- bounds
- clickable、scrollable、enabled、visible-to-user
- 父节点、子节点、兄弟节点

相同 resource-id 出现多次时，必须结合父链路、bounds、文本和 index 消歧。

### 4. 解释

解释目标节点时包含：

- 位于屏幕哪个区域
- 尺寸和点击中心点
- 父容器职责
- 关键兄弟节点
- 是否在列表、弹窗、标题栏、输入区或导航区
- 可能对应的业务职责，明确标为推断

### 5. 诊断

优先检查：

- bounds 是否相交或越界
- 透明 View 是否覆盖目标区域
- clickable 父容器是否扩大点击区域
- RecyclerView item 是否复用旧状态
- 弹窗、蒙层和业务窗口的层级关系
- 输入区是否被键盘顶起
- visible-to-user 与实际 bounds 是否矛盾

详细规则见 `diagnosis-playbook.md`。

### 6. 源码关联

按以下证据搜索：

1. resource-id
2. 自定义 View class
3. Activity 或 Fragment
4. 可见文案
5. 父容器和业务模块名称

输出 owner 候选、命中证据和置信度。没有唯一证据时不得宣称已经确定源码 owner。

### 7. 验证

修复后重新采集并比较：

- 目标节点是否存在
- bounds、width、height、center 是否变化
- 父链路是否变化
- clickable、enabled、visible 等属性是否变化
- 是否新增遮挡节点
- 页面、Activity 和键盘状态是否一致

最后使用截图确认视觉呈现，但截图不替代结构对比。

## 输出模板

```text
页面：<package / Activity / 标题>
数据源：<liv2 / xml / mcp / browser-http>
采集时间：<timestamp>

目标节点：
class：...
resource-id：...
bounds：...
尺寸：...
交互属性：...

结构关系：
父链路：...
关键兄弟：...

结论：
结构事实：...
视觉事实：...
推断：...
限制：...
```
