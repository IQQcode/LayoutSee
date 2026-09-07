# `.liv2` 格式解析原理与已知限制

本文件是 Layout Inspector Skill 的参考资料，仅在扩展 `scripts/parse_layout.py`、排查解析异常或理解 `.liv2` 编码时阅读。日常使用只看 `SKILL.md`。

## 资料来源与结论等级

本说明基于以下公开资料交叉核对：

- JetBrains Marketplace 的 LayoutInspectorV2 Pro 插件说明。
- 开源仓库 `CoXier/LayoutInspectorV2-Pro` 的 `LayoutInspectorBridge`、`LayoutFileDataParser`、`ViewNodeV2Decoder` 和 `ViewNodeV2Parser`。
- 当前项目开发过程中使用的 `.liv2` 样本和 `parse_layout.py` 解析结果。

开源源码核对版本为 commit `9fc1902a0d59a366a3250191c59ffe1df1a1aad5`，核对日期为 2026-07-13。文中“源码确认”表示可由该版本源码直接证明，“样本观察”表示截至核对日期对内部样本的观察，“当前脚本”表示现有 Python 实现的行为，三者不得混为协议规范。内部样本未随本文入库，因此样本 key 不是可独立复现的协议证据。

## 插件定位与采集流程

LayoutInspectorV2 Pro 是 Android Studio 和 IntelliJ 插件，用于抓取 Android 运行时 View 层级。它延续 Legacy Layout Inspector 的工作方式，但默认使用 Framework `ViewHierarchyEncoder` 的 V2 协议，以提高复杂页面的抓取速度。插件源码声明 V2 最低支持 API 23。

一次采集按以下顺序完成：

1. 通过设备端窗口接口加载 hierarchy，超时时间为 20 秒。
2. 按指定协议版本解析 hierarchy，确认根节点有效。
3. 以根节点为目标加载预览图，超时时间为 10 秒。
4. 将采集选项、原始 hierarchy 和预览图封装为 `.liv2` 文件。

因此 `.liv2` 同时包含结构数据和预览图，它不是单独的 View 属性字节流。

## 双层文件结构

### 外层 Java 序列化容器

源码确认 `.liv2` 由 `ObjectOutputStream` 写出，文件通常以 Java 序列化流 magic `ac ed 00 05` 开头。逻辑载荷顺序为：

```text
writeUTF(optionsJson)
writeInt(hierarchyLength)
write(hierarchyBytes)
writeInt(previewLength)
write(previewBytes)
```

`optionsJson` 至少包含：

- `version`：协议版本。插件正常采集流程默认选择 V2，但 `LayoutInspectorCaptureOptions` 的构造默认值是 V1，解析文件时必须以该字段为准。
- `title`：采集窗口标题。

`previewBytes` 由 `ImageIO` 读取，通常是设备端返回的预览图片。解析器应先正确处理 Java 序列化流的 block data，再按上述逻辑字段拆出内层 hierarchy，不能把外层控制字节当成 V2 属性。

### 内层 View hierarchy V2

`hierarchyBytes` 是 Android Framework `ViewHierarchyEncoder` 产生的 V2 数据。`ViewNodeV2Decoder` 支持以下类型标记：

- `Z`：布尔值，后跟 1 字节。
- `B`：有符号字节。
- `S`：16 位整数，也是 Map 的属性 key 类型。
- `I`：32 位整数。
- `J`：64 位整数。
- `F`：32 位浮点数。
- `D`：64 位浮点数。
- `R`：UTF-8 字符串，格式为 `R<short length><bytes>`。当前插件解码器按有符号 16 位整数读取长度，正常数据中的长度必须为非负值。
- `M`：Map 起点，内容为重复的 `S<key><typed value>`，以 short key `0` 结束。

需要特别注意，`S` 不是字符串标记，字符串只使用 `R`。Map 不是单个对象占位符，而是可递归嵌套的结构。

## 字符串表与属性 key

V2 流的顶层对象中，第一个 Map 是根 View，最后一个 Map 是字符串表。其他 View 通常通过 `meta:__child__N` 嵌套在根 View Map 下。字符串表把 short key 映射为属性全名，解析时需要反转为“属性名到 short key”的索引，再解释 View Map。

插件源码明确使用以下元属性：

- `meta:__name__`：View 类名。
- `meta:__hash__`：对象 hash，通常是整数，展示时转为十六进制。
- `meta:__childCount__`：直接子节点数量。
- `meta:__child__N`：第 N 个子节点对应的嵌套 Map。

`layoutParams` 也是嵌套 Map，不是 View 节点。插件会将其中 key `3` 解释为 LayoutParams 类名，并从 key `101` 到 `106` 中提取有效 margin 字段。

## 父子层级恢复

对于完整且合法的 V2 数据，插件解析器可以按显式元属性恢复父子层级。`ViewNodeV2Parser` 从根 View Map 开始，按 `meta:__child__N` 的序号递归创建子节点，并使用 `meta:__childCount__` 校验实际子节点数量。

当前 `parse_layout.py` 已实现外层 Java 序列化解包、字符串表反查和嵌套 Map 递归。完整解析成功时，结果标记为 `parser=v2-structured`、`hierarchy=exact`。

为兼容旧样本，脚本仍保留固定 key 扫描器。只有完整解析失败并成功进入兜底时，才调用 `infer_liv2_depth` 按 bounds 包含关系推断层级，结果标记为 `parser=legacy-key-scan`、`hierarchy=approximate`，并通过 `warning` 保留失败原因。

## 当前脚本中的样本 key

当前脚本基于真实样本使用固定 short key 提取常用字段：

- `key=3`：类全限定名。
- `key=5`：resource-id，如 `id/editor_bar`，无 id 时可能为 `NO_ID`。
- `key=8`：left。
- `key=9`：right。
- `key=10`：top。
- `key=11`：bottom。

这些编号已在现有样本中验证，但从协议设计看，属性语义应由文件尾部字符串表决定。固定编号属于兼容当前样本的捷径，不应被描述为跨版本永久稳定的协议常量。

现有样本中的 resource-id 通常不含包名前缀，例如 `id/editor_bar`，而不是 `com.baidu.tieba:id/editor_bar`。

## 当前实现限制

对用户输出结论时应如实说明：

- 当前完整解析器只支持 options 中 `version=2` 的 hierarchy。V1 文件仅尝试旧扫描器兜底。
- `writeUTF` 标题按常见 modified UTF-8 数据解码，罕见的补充字符组合仍可能显示为替换字符，但不影响 hierarchy。
- 完整解析结果的坐标根据父节点原点、父滚动量、节点 left/top 和 translation 计算，未模拟 scale、matrix、窗口 inset 和裁剪后的最终视觉区域。
- 旧扫描器依赖固定 key，插件或 Framework 输出变化后可能失效；其父子层级仍由 bounds 包含关系近似推断。
- `.liv2` 和 uiautomator XML 都不能保证覆盖所有自绘内容和 WebView 内部语义，截图只能确认视觉，不能证明 View 层级。

## 已实现解析顺序

`parse_layout.py` 当前按以下顺序处理 `.liv2`：

1. 解析 Java 序列化流，读取 options JSON、hierarchy 长度和字节、preview 长度和字节。
2. 校验 options 中的协议版本为 V2。
3. 对 V2 hierarchy 解码 `Z/B/S/I/J/F/D/R/M`。
4. 将最后一个顶层 Map 作为字符串表，反查每个 short key 的属性名。
5. 从第一个 View Map 递归解析 `meta:__child__N`，并校验 `meta:__childCount__`。
6. 从命名属性中提取 class、id、bounds、交互状态和文本。
7. 完整解析失败时运行旧固定 key 扫描器，保留近似层级和失败原因。

## 公开来源

- 插件市场：`https://plugins.jetbrains.com/plugin/21047-layoutinspectorv2-pro`
- 开源仓库：`https://github.com/CoXier/LayoutInspectorV2-Pro/tree/9fc1902a0d59a366a3250191c59ffe1df1a1aad5`
- 采集封装：`https://github.com/CoXier/LayoutInspectorV2-Pro/blob/9fc1902a0d59a366a3250191c59ffe1df1a1aad5/plugin/src/main/java/com/android/layoutinspectorv2/LayoutInspectorBridge.kt`
- 文件读取：`https://github.com/CoXier/LayoutInspectorV2-Pro/blob/9fc1902a0d59a366a3250191c59ffe1df1a1aad5/plugin/src/main/java/com/android/layoutinspectorv2/parser/LayoutFileDataParser.kt`
- V2 解码：`https://github.com/CoXier/LayoutInspectorV2-Pro/blob/9fc1902a0d59a366a3250191c59ffe1df1a1aad5/plugin/src/main/java/com/android/layoutinspectorv2/parser/ViewNodeV2Decoder.kt`
- 层级恢复：`https://github.com/CoXier/LayoutInspectorV2-Pro/blob/9fc1902a0d59a366a3250191c59ffe1df1a1aad5/plugin/src/main/java/com/android/layoutinspectorv2/parser/ViewNodeV2Parser.kt`
