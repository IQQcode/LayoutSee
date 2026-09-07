# uiautodev 浏览器 HTTP 实时采集

## 原理

`python3 -m uiautodev` 启动本机 FastAPI 服务，默认监听 `127.0.0.1:20242`。uiautodev 网页通过 CORS 访问该服务。Agent 可使用 ego-browser 打开 `https://uiauto.devsleep.com`，在网页 JavaScript 上下文中执行 `fetch()`。

```text
设备
  → uiautodev driver
  → FastAPI 127.0.0.1:20242
  → 浏览器 fetch
  → hierarchy XML
  → DOMParser
  → View 结构分析
```

该链路不经过 Desktop MCP。每次 hierarchy 请求都重新采集当前页面。

## 核心接口

- `GET /api/info`：服务版本和可用 driver。
- `GET /api/android/list`：设备列表。
- `GET /api/android/{serial}/command/currentApp`：package、Activity、pid。
- `GET /api/android/{serial}/hierarchy`：JSON hierarchy。
- `GET /api/android/{serial}/hierarchy?format=xml`：原始 uiautomator XML。
- `GET /api/android/{serial}/screenshot/0`：当前屏幕截图。

`/api/android/features`、`/{serial}/current_activity`、`/{serial}/source`、`/{serial}/dump`、`/{serial}/xml` 等路由在 0.5.0 本机实测可能返回 404，不属于核心依赖。

## 标准流程

1. 在浏览器上下文请求 `/api/info`，确认状态为 200。
2. 请求 `/api/android/list`。
3. 动态选择 `enabled=true` 的设备，记录 serial、model、name。
4. 请求 `/command/currentApp`。
5. 立即请求 `/hierarchy?format=xml`。
6. 使用 `DOMParser` 解析所有 `node`。
7. 提取 class、resource-id、package、text、content-desc、bounds 和交互属性。
8. 如需视觉确认，再请求 `/screenshot/0`。

核心示例：

```javascript
const base = "http://127.0.0.1:20242";
const devices = await fetch(`${base}/api/android/list`).then(r => r.json());
const serial = devices.find(device => device.enabled)?.serial;
const currentApp = await fetch(
  `${base}/api/android/${serial}/command/currentApp`
).then(r => r.json());
const xml = await fetch(
  `${base}/api/android/${serial}/hierarchy?format=xml`
).then(r => r.text());
const document = new DOMParser().parseFromString(xml, "text/xml");
const nodes = Array.from(document.querySelectorAll("node"));
```

## 端口与 serial

服务地址默认固定：

```text
http://127.0.0.1:20242
```

设备断线、重新插拔 USB、adb reconnect 或更换测试机通常不会改变服务端口，但会改变设备列表或 serial。因此：

```text
服务地址固定
设备 serial 每次动态发现
hierarchy 每次实时抓取
```

只有 uiautodev 版本、启动参数、端口冲突、容器或远程主机环境变化时，才需要重新确认地址。

## 断线重连

```text
/api/info
  → /api/android/list
  → 确认 enabled=true
  → 重新读取 serial
  → /command/currentApp
  → /hierarchy?format=xml
```

禁止复用断线前 hierarchy。

## 一致性与失败处理

- `/api/info` 失败：本地服务未运行或地址不可达。
- 设备列表为空：当前没有可用设备。
- `enabled=false`：设备不可用于实时分析。
- currentApp 或 hierarchy 非 200：刷新设备列表后重试一次。
- XML 解析失败：报告原始状态，不输出旧页面结论。
- currentApp 与 XML 页面证据冲突：说明采集期间发生跳转，整批丢弃并重采。
- 404 的非核心接口不影响 hierarchy 主链路。

## 数据安全

页面树可能包含聊天消息和账号信息。只输出页面判断、目标节点和必要文本摘要，不默认保存完整响应。
