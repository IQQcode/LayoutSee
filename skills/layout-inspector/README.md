# Layout Inspector Skill

面向 AI Agent 的 Android 运行时 View 树感知工具。解析 `.liv2` 和 uiautomator XML 快照，输出结构化控件树、精确坐标和真实层级关系，支持设备实时布局读取。

## 概览

当 AI 需要理解 Android 页面"屏幕上到底放了什么、放在哪里、有多大、能不能点"时，Layout Inspector 提供 View 树级别的结构证据，而不是靠截图猜测。

**核心价值：**

- 解析 LayoutInspectorV2-Pro 插件导出的 `.liv2` 文件，打通 V2 协议，恢复精确父子层级
- 兼容 uiautomator dump 的 hierarchy XML
- 支持 Uiautodev Desktop MCP 和浏览器 HTTP 实时读取设备布局
- 输出统一坐标格式 `[left, top, right, bottom]`，可直接用于控件定位

**能力边界：**

- 能回答："editor_bar 的 bounds 是多少、它的父容器是谁、有没有兄弟节点覆盖它"
- 不能回答："为什么这个文字显示不全"（需要结合截图和源码判断）
- 不支持静态 layout XML 源码阅读和 iOS 视图调试

## 案例

### 案例 1：定位发布器输入框尺寸

```bash
python3 .comate/skills/layout-inspector/scripts/parse_layout.py editor.liv2 --json --filter editor_bar
```

输出：

```json
{
  "class": "EditText",
  "fqcn": "android.widget.EditText",
  "bounds": [0, 1800, 1080, 1920],
  "depth": 3,
  "labels": ["id/editor_bar"],
  "flags": ["clickable", "enabled"]
}
```

结果：输入框占用屏幕底部 1800-1920 像素区域，点击区域正常。

### 案例 2：验证修复后弹窗不再遮挡按钮

修复前：

```bash
python3 parse_layout.py before_fix.liv2 --json --filter submit_btn
# bounds=[0, 1600, 360, 1700]
python3 parse_layout.py before_fix.liv2 --json --filter dialog_mask
# bounds=[0, 0, 1080, 2340], depth 比 submit_btn 浅
```

结论：`dialog_mask` 覆盖整个屏幕，`submit_btn` 被遮挡。

修复后重新 dump 并对比，确认 `dialog_mask` 已消失或 depth 在 `submit_btn` 之下。

### 案例 3：解析 uiautomator XML

```bash
python3 parse_layout.py hierarchy.xml --filter TextureView
```

输出所有 TextureView 节点的 class、text、content-desc 和 bounds。

## 依赖安装

### 解析脚本（必需）

Python 3 标准库即可运行，无需额外安装依赖：

```bash
python3 --version  # 需要 3.8+
```

### LayoutInspectorV2-Pro 插件（生成 .liv2 必需）

在 Android Studio 中安装：

1. Settings / Preferences → Plugins → Marketplace
2. 搜索 `LayoutInspectorV2-Pro`
3. 安装后重启 Android Studio

或从插件市场下载：https://plugins.jetbrains.com/plugin/21047-layoutinspectorv2-pro

安装验证：

```bash
while IFS= read -r jar; do
  if unzip -p "$jar" META-INF/plugin.xml 2>/dev/null | grep -q 'com.eric-li.layout-inspector-v2'; then
    echo "已安装"; break
  fi
done < <(find ~/Library/Application\ Support -maxdepth 6 -path '*AndroidStudio*/plugins/*' -name '*.jar' 2>/dev/null)
```

未安装时，只解析 uiautomator XML 也可正常使用。

### Uiautodev（实时读取设备布局，可选）

```bash
pip install uiautodev
python3 -m uiautodev  # 启动 HTTP 服务，默认端口 20242
```

### adb（导出 uiautomator XML，可选）

```bash
adb shell uiautomator dump
adb pull /sdcard/window_dump.xml
```
