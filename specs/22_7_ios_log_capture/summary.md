# iOS 日志抓取（syslog）总结

## 问题描述

用户连接 iOS 测试机后，工作台没有任何日志抓取能力：Android 有 `android-logcat` 插件 + `/devices/{id}/logcat` 增量端点，iOS 侧完全缺位；终端 Tab 只支持 adb shell，对 iOS 无 shell 可用。需要 iOS 对标 `adb logcat | grep xxx` 的日志抓取能力，并配套新增插件支持过滤抓取。

## 根因分析

功能缺位（非缺陷）：iOS 没有「事后 dump 环形缓冲」的等价命令（`adb logcat -d` 无对应物），日志只能走实时流协议——真机是 lockdown 服务 `com.apple.syslog_relay` 的文本流，模拟器是 `xcrun simctl spawn <udid> log stream`——两者都需要新链路，而既有 `LogcatHub` 的「周期 dump + 锚点对齐」模型不适配。

## 方案结论

调研（anysearch 查证 idevicesyslog.c / pymobiledevice3 / tidevice 源码级细节 + 本机模拟器实测）后采用（三决策用户已确认）：

1. **复用 `/logcat` 端点与 `$u.device.logcat` 桥**：server 按 device platform 分派到新 `SyslogHub`；桥、bridgeHost、契约零改动。
2. **真机 = lockdown + syslog_relay 文本流**（纯 Python 标准库，零第三方依赖）：usbmux 隧道 → lockdown（4 字节大端 plist 成帧）→ QueryType → ReadPairRecord（usbmuxd 消息）→ StartSession → StartService → 新隧道读流；行分隔 `\n\x00`，**vis(3) 转义必须解码否则中文日志乱码**（pymobiledevice3 2025 年才修的坑）。
3. **模拟器 = `simctl spawn <udid> log stream --style json --level debug`**：实测 json style 才带级别（syslog/compact style 无级别列）；顶层 JSON 对象用深度计数 + 字符串感知提取。
4. **条目形状与 Android 同构**（`tag`=进程名），插件 UI 代码近乎零改动复用；iOS 级别序 D/I/W/E/F（无 V）。
5. **SyslogHub = 每设备持续流读取线程**（懒启动、断流自愈、generation 代际重连、环形缓冲 4000）。
6. **iOS clear = 本地缓冲重置**（不触碰设备状态），分派在只读拦截之前；插件 UI 的「清空显示」是纯前端清屏，不调 `logcatClear`。

已知系统限制（写入插件文案）：os_log 私有内容显示 `<private>`（系统脱敏无法绕过）；真机 syslog_relay 仅实时流无历史回放。

## 已完成内容

- 调研并验证 iOS 双端日志抓取技术路线（含本机 booted 模拟器实测 json 格式）
- Core：`ios/lockdown.py`（lockdown 握手 + TLS + 配对记录）、`ios/syslog.py`（vis 解码 / 行解析 / 模拟器 JSON 提取 / SyslogHub）、`SimctlClient.log_stream`、server platform 分派、bootstrap 装配
- 插件：`repos/plugins/ios-logcat/` 四件套（AS 风格过滤、iOS 级别序、清空显示、暂停/点行停滚/soft-wrap/导出）
- 文档：根 `INDEX.md` 与 `source/plugins/overview.md` 登记新插件
- 附带收口：contracts 夹具 productVersion 22.6.1→22.7.0（f13f316 升版漏更导致 test:contracts 既有红）

## 改动文件

- `repos/core/src/layoutsee_core/ios/lockdown.py`，新增：lockdown 客户端（握手/TLS/配对记录读取）
- `repos/core/src/layoutsee_core/ios/syslog.py`，新增：vis 解码、真机行解析、模拟器 JSON 提取、SyslogHub 双端 Hub
- `repos/core/src/layoutsee_core/ios/simctl.py`，扩展：`log_stream(udid)`（argv 校验 + start_new_session）
- `repos/core/src/layoutsee_core/server.py`，修改：`_read_logcat`/`_clear_logcat` platform 分派、CoreContext 增 `syslog` 字段
- `repos/core/src/layoutsee_core/bootstrap.py`，修改：装配 SyslogHub
- `repos/core/tests/test_ios_syslog.py`，新增：33 用例（vis/行解析/JSON 提取/Hub 游标语义/lockdown 握手替身）
- `repos/core/tests/test_ios_capture.py`，修改：StubSyslogHub 注入 + iOS logcat 分派/清空审计用例（替换 2 个旧口径用例）
- `repos/plugins/ios-logcat/{manifest.json,index.html,app.js,style.css}`，新增：插件四件套
- 根 `INDEX.md` / `source/plugins/overview.md`，加行：插件登记
- `repos/contracts/fixtures/{valid/info-envelope.json,invalid/info-invalid-nonce.json}`，修改：productVersion 同步 22.7.0

## 验证结果

- [x] `npm run test:core`：220 用例全绿（含 iOS syslog 33 例 + 分派/审计用例）
- [x] `npm run lint` 通过；`npm run contracts:check` 无漂移；`npm run test:web` 18 pass；`npm run test:contracts` 7 pass（夹具修复后恢复全绿）
- [x] 模拟器链路端到端冒烟：真实 Core + booted 模拟器（3249070E），SyslogHub 增量读出真实日志（D 级 locationd 等，游标/清理正常）；插件以 `origin: builtin`、`devicePlatforms: ["ios"]` 正确入 `/api/v1/plugins/index`
- [x] 双 review：规格符合性（8 条验收逐条实测）与代码质量（并发/资源/安全走查）均 PASS_WITH_NOTES；P2 项（decode_vis 八进制 `\777` 越界 ValueError）已修复并补对抗回归
- [ ] **真机（USB 测试机）联调**：本机无真机在场，lockdown/syslog_relay 链路仅有替身单测覆盖——待用户接真机在工作台打开「日志抓取」卡片做最终可视化确认（重点看中文日志可读性与 process: 过滤）

## 后续建议

1. **真机联调**：USB 连接已配对测试机 → 工作台选 iOS 设备 → 插件卡片「日志抓取」→ 验证中文日志、过滤、暂停/导出；若 StartService 被拒按提示用 Xcode/Finder 重新配对
2. MCP 侧如需日志工具（tools/call 形态），可在 SyslogHub 之上加一个只读工具（本 spec 明确不做）
3. 多台 booted 模拟器目前报 `CORE_UNAVAILABLE`，未来可用 `simctl listports` 类手段做 UDID↔port 映射
4. `state["error"]` 死状态已在 review 中移除；若未来要在 UI 呈现「流断开原因」，在 read 返回体加 `error` 字段即可（pump 已有错误上下文）
