# Android 布局诊断模板

## 重叠与遮挡

证据：

- 两个节点 bounds 相交。
- 上层节点覆盖目标节点区域。
- 覆盖节点可能透明，但占据相同坐标。
- 目标节点 visible=true 不代表没有被兄弟节点遮挡。

输出重叠矩形、覆盖比例、节点层级和 clickable 属性。

## 点击区域异常

检查：

- 目标节点自身 clickable。
- clickable 是否落在父容器。
- 父容器 bounds 是否明显大于视觉元素。
- 透明节点是否 clickable。
- 多个可点击节点是否区域重叠。

不能只根据图标 bounds 判断实际点击区域。

## 越界与裁剪

检查：

- 子节点 bounds 是否超出父节点。
- 是否存在 clipChildren、translation 或动画导致的视觉偏移。
- `.liv2` 坐标异常时先查看 `parser` 和 `hierarchy`；不能把 `legacy-key-scan` 的近似层级当作真实父子关系。

## RecyclerView 与列表复用

检查：

- 相同 resource-id 是否出现在多个 item。
- item bounds 是否重复、重叠或残留在屏幕外。
- visible、enabled、selected 等状态是否与当前位置一致。
- 诊断结论应结合 item 父链路和 position 证据。

## 弹窗与蒙层

检查：

- hierarchy 是否包含多个 package 或窗口根节点。
- 蒙层是否覆盖业务窗口。
- 弹窗外区域是否 clickable。
- 系统窗口、侧屏面板、输入法和业务弹窗要分开描述。

## 键盘与输入区

证据：

- 输入区底部 bounds 是否接近屏幕底部。
- 页面可用高度是否缩小。
- 输入法 package 或窗口节点是否出现。
- 输入区是否整体上移。

只有结构证据不足时，才用截图判断键盘状态，并标记为视觉推断。

## WebView 与自绘内容

uiautomator 可能只返回 WebView 容器或忽略 Canvas 内部元素。此时：

1. 先说明 View 树能力边界。
2. 使用浏览器 CDP、OCR 或截图补充语义。
3. 不为视觉元素虚构 resource-id 或原生父链路。

## 源码关联

按 resource-id、自定义 class、Activity、Fragment 和文案搜索 owner。输出：

- 候选文件或类。
- 命中证据。
- 置信度。
- 仍需验证的假设。

## 结论分层

```text
结构事实：直接来自 View 树。
视觉事实：直接来自截图。
推断：结合结构、视觉和业务知识得出的解释。
限制：数据源无法覆盖的内容。
```
