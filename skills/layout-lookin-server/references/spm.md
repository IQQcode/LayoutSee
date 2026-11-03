# SPM 集成

适用：工程无 `Podfile`、有 `.xcodeproj`（摸底 `verdict = recommend-spm`）。URL 与版本规则事实源：[Package.swift](https://github.com/QMUI/LookinServer/blob/develop/Package.swift)、[官方 SPM Demo](https://github.com/QMUI/LookinServer/tree/develop/LookinDemo)。

## 关键规则

- 仓库 URL：`https://github.com/QMUI/LookinServer`；版本规则 **`upToNextMajorVersion` + `minimumVersion 1.2.8`**。
- **Release 安全由包内宏保证**（Package.swift 用 `.when(configuration: .debug)` 裁剪整段 server 代码），全配置引入即可；Xcode 工程的包依赖不支持按 build configuration 加条件（`XCSwiftPackageProductDependency` 只有 `platformFilters`），**不要尝试也不要需要**任何 Release 排除操作。
- Swift / OC 项目在 SPM 下无差别（包内已含 Swift target）。

## 方式 A：Xcode UI（优先推荐给用户）

1. Xcode 打开工程 → File → Add Package Dependencies…
2. 搜索框输入 `https://github.com/QMUI/LookinServer` → Add Package
3. Dependency Rule 选 **Up to Next Major Version**，起始版本 `1.2.8` → Add Package
4. 勾选 App target → Add Package
5. 构建一次确认通过，然后进 SKILL.md 运行验收。

## 方式 B：AI 直改 project.pbxproj

仅当用户明确要求脚本化集成时使用；改前确认工程有版本管理（或先做副本 `project.pbxproj.bak`），改完展示 diff。以官方 Demo（objectVersion 55）为参照，共五段，UUID 用 24 位十六进制且全局唯一：

1. `PBXProject` 的 `packageReferences` 数组新增引用：
   ```
   packageReferences = (
       AAAA1111BBBB2222CCCC3333 /* XCRemoteSwiftPackageReference "LookinServer" */,
   );
   ```
2. 新增 section（文件中若无 `/* Begin XCRemoteSwiftPackageReference section */` 则整段新建，放在注释对内）：
   ```
   /* Begin XCRemoteSwiftPackageReference section */
   AAAA1111BBBB2222CCCC3333 /* XCRemoteSwiftPackageReference "LookinServer" */ = {
       isa = XCRemoteSwiftPackageReference;
       repositoryURL = "https://github.com/QMUI/LookinServer";
       requirement = {
           kind = upToNextMajorVersion;
           minimumVersion = 1.2.8;
       };
   };
   /* End XCRemoteSwiftPackageReference section */
   ```
   `kind` 合法值：`upToNextMajorVersion` / `upToNextMinorVersion` / `exactVersion`（配 `minimumVersion`）、`range`、`branch`、`revision`。
3. 目标 `PBXNativeTarget` 新增：
   ```
   packageProductDependencies = (
       BBBB1111CCCC2222DDDD4444 /* LookinServer */,
   );
   ```
4. 新增 section：
   ```
   /* Begin XCSwiftPackageProductDependency section */
   BBBB1111CCCC2222DDDD4444 /* LookinServer */ = {
       isa = XCSwiftPackageProductDependency;
       package = AAAA1111BBBB2222CCCC3333 /* XCRemoteSwiftPackageReference "LookinServer" */;
       productName = LookinServer;
   };
   /* End XCSwiftPackageProductDependency section */
   ```
5. 新增 `PBXBuildFile` 并把它加进 App target 的 `PBXFrameworksBuildPhase` 的 `files`：
   ```
   CCCC1111DDDD2222EEEE5555 /* LookinServer in Frameworks */ = { isa = PBXBuildFile; productRef = BBBB1111CCCC2222DDDD4444 /* LookinServer */; };
   ```
   ```text
   files = (
       ...
       CCCC1111DDDD2222EEEE5555 /* LookinServer in Frameworks */,
   );
   ```

注意：官方 Demo 里存在一条**不带 `package` 字段**的 `XCSwiftPackageProductDependency`，是 UI 操作残留，直改时只保留带 `package` 引用的一条，避免双重链接。

## 验证

```bash
xcodebuild -resolvePackageDependencies -project <工程>.xcodeproj -scheme <scheme>
```

成功后 Xcode 会在工程目录生成 `xcuserdata`/package 缓存；再构建 Debug 配置确认编译通过，然后进 SKILL.md 运行验收。纯 SwiftPM 包工程（无 xcodeproj）不适用本 skill：LookinServer 服务于 iOS App target，请回到 Xcode 工程形态集成。
