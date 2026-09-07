# 使用前检查：LayoutInspectorV2-Pro 插件

`.liv2` dump 文件由 Android Studio 插件 **LayoutInspectorV2-Pro** 导出：
https://plugins.jetbrains.com/plugin/21047-layoutinspectorv2-pro

当用户要用本 skill 解析 `.liv2` 文件时，**先检查本机 Android Studio 是否装了该插件**。
没装则提示用户安装，否则用户无法产出 `.liv2` 快照。
（只解析 uiautomator XML 时不需要此插件，可跳过检查。）

## 插件标识（判断依据）

- 插件 id：`com.eric-li.layout-inspector-v2`
- 插件名：`LayoutInspectorV2-Pro`
- 安装后目录名是通用的 `plugin`（不是插件名），**不能靠目录名判断**，
  要靠 jar 内 `META-INF/plugin.xml` 的 `<id>` 识别。

## Mac 默认安装位置

用户插件装在 Android Studio 配置目录下的 `plugins/`：

- 新版（2020.3+）：`~/Library/Application Support/Google/AndroidStudio<版本>/plugins/`
  （如 `AndroidStudio2025.2.3`）
- 旧版：`~/Library/Application Support/AndroidStudio<版本>/plugins/`

插件 jar 通常落在 `plugins/plugin/lib/plugin-<版本>.jar`。

## 检测命令

在本机跑以下命令，遍历所有 Android Studio 配置目录，按 plugin id 判断是否已安装：

用 `find` 一次覆盖新版（`Google/AndroidStudio*`）和旧版（`AndroidStudio*`）配置目录，
避免 glob 在 zsh 下 `no matches found` 报错：

```bash
found=""
while IFS= read -r jar; do
  if unzip -p "$jar" META-INF/plugin.xml 2>/dev/null \
      | grep -q 'com.eric-li.layout-inspector-v2'; then
    found="$jar"; break
  fi
done < <(find ~/Library/Application\ Support -maxdepth 6 \
              -path '*AndroidStudio*/plugins/*' -name '*.jar' 2>/dev/null)
if [ -n "$found" ]; then
  echo "已安装 LayoutInspectorV2-Pro: $found"
else
  echo "NOT_INSTALLED"
fi
```

遍历 jar 里的 plugin.xml 需要几秒，属正常。

## 未安装时的提示

输出结果为 `NOT_INSTALLED` 时，明确告知用户并给出安装指引：

> 本机 Android Studio 未检测到 **LayoutInspectorV2-Pro** 插件，无法导出 `.liv2` 快照。
> 请先安装：Android Studio → Settings/Preferences → Plugins → Marketplace，
> 搜索 `LayoutInspectorV2-Pro` 安装，或访问
> https://plugins.jetbrains.com/plugin/21047-layoutinspectorv2-pro 下载，装好后重启 Android Studio。

已安装则直接继续按 SKILL.md 流程解析 `.liv2`。
