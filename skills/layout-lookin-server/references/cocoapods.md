# CocoaPods 集成

适用：工程已有 `Podfile`（摸底 `verdict = recommend-cocoapods`）。

## Podfile 写法

加到 **App target** 的依赖块内（不要加到注释块或别的 target）：

```ruby
# Swift 项目（展示 Swift 属性名需要 Swift subspec）
pod 'LookinServer', '1.2.8', :subspecs => ['Swift'], :configurations => ['Debug']

# Objective-C 项目
pod 'LookinServer', '1.2.8', :configurations => ['Debug']
```

- **版本写死 `'1.2.8'`**：LayoutSee pin 协议版本 7（覆盖 1.1.8 ~ 1.2.8），锁精确版本避免未来协议漂移。
- 混合项目按 Swift 项目写法；对稳定性敏感可选 `SwiftAndNoHook` subspec（牺牲 UIImage 名称与 UIVisualEffectView 样式两个 hook 功能）。
- 与 `use_frameworks!` 无关，静态库方式也能用（需 LookinServer ≥ 1.1.0）。

## `:configurations` 的坑（最容易翻车的一步）

数组里的名字必须与工程 target 的 build configuration 名**精确匹配**。默认工程是 `['Debug']`；如果 App 用自定义 Debug 变体（`Dev`、`Staging`、`Dev-Debug`…），必须把真实名字加进数组，否则 LookinServer 不会链入实际运行的那个配置，LayoutSee 将找不到 App。

- 工程有哪些 configuration：用 `inspect_ios_project.py` 输出的 `configurations`（含 `debugLike` 标记），不要猜。
- 若同时写多个 configuration 且报错 `The subspecs of LookinServer are linked to different build configurations`：这是 CocoaPods 对 subspecs × configurations 组合的限制（[LookinServer#134](https://github.com/QMUI/LookinServer/issues/134)），对策是减少 subspecs 声明（OC 写法）或改用组合 subspec（如 `SwiftAndNoHook`）。
- **绝不能包含 Release 或等价发布配置**：CocoaPods 集成时 pod 内 `SHOULD_COMPILE_LOOKIN_SERVER=1` 是无条件定义的，Debug-only 完全靠这个数组挡。

## 操作步骤

1. 摸底拿 `podfileTargets` 与 `configurations`，确认语言（Swift / OC）。
2. 编辑 Podfile：定位 App target 的 `target '...' do ... end` 块，按上述写法插入 pod 行，缩进对齐既有行。
3. 征得同意后运行：`pod install`（在 Podfile 所在目录）。需要 CocoaPods（`pod --version` 不可用时先装：`brew install cocoapods` 或 `gem install cocoapods`，先征求用户同意）。
4. 验证：`Podfile.lock` 出现 `LookinServer (1.2.8)`；`xcodebuild` 打开工程构建 Debug 配置应通过。
5. 进 SKILL.md 第 4 步运行验收。

## 常见失败

| 现象 | 原因与处理 |
| --- | --- |
| `pod install` 报 subspecs linked to different build configurations | 见上节 issue #134 对策 |
| 构建报 duplicate symbols | LookinServer < 1.0.5 的老版本问题；用 1.2.8 |
| 静态库集成编译失败 | LookinServer < 1.1.0；用 1.2.8 |
| Release 构建把 LookinServer 编进去 | `:configurations` 漏配或含发布配置，回查数组 |
