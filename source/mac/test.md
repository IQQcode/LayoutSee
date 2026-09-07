# mac 测试

```bash
npm run test:mac
```

覆盖合法 READY 解析、nonce/长度/版本拒绝、READY 与 info 进程身份不一致，以及会话令牌派生（与 Core 侧共享金样值，防止两端算法漂移）。静态检查与单元测试不等同于 Electron 端到端验证；壳生命周期、进程回收与安全边界需要 Playwright + 假 Core 接缝（属后续 Story 测试基建）。

## 手动功能测试提示

- 直接双击 DMG 内的 LayoutSee.app（或 `release/mac-arm64/LayoutSee.app`）。
- 观察启动页 → Core 就绪 → 设备页的完整链路；15 秒未就绪会进入错误页。
- 设备页每 5 秒刷新；连接 Android 真机后 3 秒内应出现设备行。
- 工作台画面为截图轮询模式；抓取快照后元素查看 Tab 展示树、属性与 XPath。
- 退出应用后检查无残留 `layoutsee-core` 进程（`pgrep -f layoutsee-core`）。
