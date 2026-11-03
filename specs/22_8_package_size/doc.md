# 22.8 包体积优化（设计）

## 背景与目标

DMG 分发体积偏大：arm64 136M / x64 141M。**红线：不影响任何功能与现有交互逻辑。**

体积构成实测（22.7.0 基线）：~91% 是 Electron 44 运行时本体（压缩态 124-128M），自研 payload 解压后仅 ~31M（PyInstaller Core onedir 27-30M + web 604K + asar 70K）。打包链路本身无冗余泄漏（无 venv、无测试代码、无双架构混包），优化空间在「裁剪 + 压缩」而非「去重」。

## 设计决策

### 1. Electron 多语言资源裁剪（after-pack）

Electron 44 分发 44 种语言 ×（主目录 + 3 个语法性别变体），locale.pak 位于
`Electron.app/Contents/Frameworks/Electron Framework.framework/Versions/A/Resources/*.lproj`
（app 顶层 Resources 下的 `.lproj` 全为空目录），合计 **~50MB 未压缩**。

- 保留白名单：`en.lproj` / `zh_CN.lproj` / `zh_TW.lproj`，其余全删（两处：app 顶层 Resources + Framework 内 Resources）。
- 功能影响评估：应用界面文字全部由代码自绘，不依赖这些资源；唯一变化是系统级弹窗（保存面板、权限提示等）在系统语言非中英时回退英文。已获用户确认。

### 2. PyInstaller 收紧

- `--strip`：去收集的 so/dylib 符号表（libpython3.12.dylib 18M 里占比可观）。
- `--exclude-module setuptools`：PyInstaller hook 拖进来的空壳，运行时无依赖。
- 决策门：strip 后必须 Core 独立启动 READY 正常，异常回退（已验证，见 summary）。
- **不做**：strip Electron Framework 本体（崩溃风险）、动 icudtl.dat / libffmpeg.dylib / v8 snapshot（功能红线）。

### 3. DMG 压缩格式：UDZO → ULMO 后处理

实测（同一分区数据，22.7.0 arm64 基线 135.6M）：

| 格式 | 体积 | 结论 |
|---|---:|---|
| UDZO（electron-builder 默认，zlib） | 135.6M | 基线 |
| ULFO（lzfse 仅文件数据，electron-builder 原生支持） | 144.0M | 反而更大，否决 |
| ULMO（完整块级 lzfse，`hdiutil convert` 后处理） | 112.0M | **-17.4%，胜出** |

- electron-builder 26.15.7 的 `dmg.format` 枚举不含 ULMO（含 ULFO/UDBZ），故走后处理：package.mjs 归档前对 UDZO 产物 `hdiutil convert -format ULMO` 替换（convert 耗时 ~9s/包）。
- ULMO 需 macOS 10.15+，产品下限 13.0，无兼容问题。
- blockmap 因后处理失效且产品无自动更新：`dmg.writeUpdateInfo: false` 停生成 + 归档时兜底清理。
- 实施坑：`hdiutil convert -o` 会自动补 `.dmg` 后缀，输出名必须带 `.dmg` 结尾。

### 4. 体积观测

package.mjs 收尾打印每架构 `core onedir` 与 DMG 体积（du 换算），发版时可对照本 summary 的基线表防回归。

## 明确不做

- web bundle 分包（478K 占比 <0.5%）、icns 缩减（全尺寸必需）、双架构交付口径调整（产品决策）、`poetry.lock` 历史遗留清理（超范围）。
