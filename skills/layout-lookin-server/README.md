# LookinServer 集成 Skill（layout-lookin-server）

自动把 [LookinServer](https://github.com/QMUI/LookinServer)（QMUI 开源的 iOS 视图调试框架）集成进用户自己的 iOS 工程，使 LayoutSee 能抓取该 App 的运行时视图树。

## 概览

- **摸底**：一条命令识别工程形态（CocoaPods / SPM）、语言（Swift / OC）、build configuration 名、是否已集成
- **集成**：按路径改 `Podfile`（CocoaPods）或 `project.pbxproj`（SPM），版本锁定 `1.2.8`、仅 Debug
- **验证**：`pod install` / `xcodebuild -resolvePackageDependencies` + Debug 构建运行
- **验收**：LayoutSee 设备列表出现 iOS 设备；连接类故障见 troubleshooting

## 快速上手

```bash
python3 -I scripts/inspect_ios_project.py /path/to/ios-project
```

输出 JSON：`verdict`（`recommend-cocoapods` / `recommend-spm` / `cocoapods-integrated` / `spm-integrated` / …）、各 .xcodeproj 的 `configurations`、语言占比。后续步骤见 `SKILL.md`。

## 环境依赖

- macOS + 用户的 iOS 工程；脚本仅依赖 Python 3 标准库，只读。
- CocoaPods 路径需要 CocoaPods（`pod`）；SPM 路径需要 Xcode。
- 集成完成后的抓取需要 LayoutSee 桌面应用（环境体检见 `layout-env` skill）。

## 文档

- 工作流程与版本事实：`SKILL.md`
- CocoaPods 集成：`references/cocoapods.md`
- SPM 集成（含 pbxproj 结构）：`references/spm.md`
- 连接类故障排查：`references/troubleshooting.md`
- 环境体检：`layout-env` skill；视图树抓取：`layout-see` skill
