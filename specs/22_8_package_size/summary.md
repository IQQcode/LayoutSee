# 22.8 包体积优化（实施总结）

日期：2026-11-04。分支：`v22.8.0_dev_deploy`。

## 体积前后对比

| 产物 | 优化前（22.7.0 基线） | 优化后 | 收益 |
|---|---:|---:|---:|
| arm64 DMG | 136.0M | **96.0M** | **-40M（-29%）** |
| x64 DMG | 141.0M | **112.0M** | **-29M（-21%）** |
| core onedir arm64 | 27M | 26.1M | -0.9M |
| core onedir x64 | 30M | 27.8M | -2.2M |

收益构成：ULMO 压缩（-17% 量级）> .lproj 裁剪（解压态 ~48M）> PyInstaller strip（1-2M）。

## 代码变更

| 文件 | 变更 |
|---|---|
| `repos/mac/scripts/after-pack.cjs` | 新增 `.lproj` 裁剪（白名单 `en.lproj`/`zh_CN.lproj`/`zh_TW.lproj`），app 顶层 Resources + Electron Framework 内 Resources 两处 |
| `repos/mac/scripts/package.mjs` | ① PyInstaller 加 `--strip` + `--exclude-module setuptools`；② 归档前 UDZO→ULMO 后处理；③ 停用/兜底清理 blockmap；④ 收尾体积日志 |
| `repos/mac/electron-builder.yml` | `dmg.writeUpdateInfo: false`（后处理致 blockmap 失效，产品无自动更新） |

## 验证记录（非可视化，红线保障）

- 回归：`npm run test:unit` 223 tests OK；`@layoutsee/mac` 8 tests OK。
- arm64：DMG 挂载 → 拷出 .app → Core 独立启动 **3s READY**（strip 后 libpython 正常）；Electron 壳 `open` 启动 → 壳 + Helper + 壳拉起的 Core 全部在跑 → osascript 优雅退出无残留。
- x64：同流程，Core 在 Rosetta 下 **7s READY**。
- lproj 抽查：双架构两处目录均只剩 en/zh_CN/zh_TW。

## 已知坑（复用提示）

1. `hdiutil convert -o PATH` 自动补 `.dmg` 后缀——输出名必须以 `.dmg` 结尾，否则 rename 报 ENOENT。
2. electron-builder 打包偶发 `Timeout awaiting 'request' for 600000ms`：用 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/` 前缀重试（INDEX.md 既有对策）。
3. 根 package.json 无 `package:mac:x64` script，单打 x64 要走 `npm --workspace @layoutsee/mac run package:mac:x64`。

## 待人工确认（可视化验收）

用户侧抽查：明暗主题、设备页/工作台/插件页交互、原生菜单与「关于」面板、保存文件对话框（非中英系统语言下回退英文属预期行为）。
