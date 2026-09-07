# web 构建与启动

```bash
npm install
npm run dev:web                              # 推荐：Core + vite 一起起，浏览器直接可写
npm --workspace @layoutsee/web run build
```

生产构建输出位于 `repos/web/dist`，由 Core 同源托管；`/api`、`/ws`、`/mcp` 路径不参与 SPA 回退。

## 浏览器联调（dev:web）

`npm run dev:web`（根目录，实现在 `scripts/dev-web.mjs`）做四件事：生成 nonce → 起 Core（不带 `--static-dir`）→ 读 READY 行按握手金样派生会话令牌 → 起 vite 并把令牌注入 `VITE_LAYOUTSEE_SESSION`。打开打印出的 `http://127.0.0.1:4173` 即可跑通抓取、点击、终端等写链路。

`vite.config.mjs` 把 `/api`、`/mcp`、`/health` 代理到 Core，并在转发时摘掉 `Origin`（Core 对跨源 Origin 会拒绝，无 Origin 放行）。

## 生产形态

Core 带 `--static-dir repos/web/dist` 启动，打开 READY 行里的 `http://127.0.0.1:{port}`。会话令牌由 Core 在托管首页时替换进 `<meta name="layoutsee-session">`，无需手工配置。只支持回环地址访问：换成局域网 IP 既连不上（Core 只 bind 127.0.0.1），也会因为不是 secure context 而丢掉 `crypto.randomUUID`、剪贴板与 WebCodecs。

单跑 `npm --workspace @layoutsee/web run dev` 只有页面骨架，`/api` 无代理且无令牌，写请求会被 Core 拒绝。
