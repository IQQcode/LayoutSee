import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev 下 API 不在 vite 里，代理到 dev:web 拉起的 Core（默认端口 11663）
const corePort = Number(process.env.LAYOUTSEE_CORE_PORT) || 11663;
const coreTarget = `http://127.0.0.1:${corePort}`;

// Core 会校验 Host 与 Origin。changeOrigin 把 Host 改成 Core 的地址；
// Origin 仍是 vite 的 4173，属于跨源，dev 下直接摘掉让 Core 走「无 Origin」放行分支。
const proxyToCore = {
  target: coreTarget,
  changeOrigin: true,
  configure: (proxy) => {
    proxy.on("proxyReq", (proxyReq) => proxyReq.removeHeader("origin"));
  },
};

export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false },
  define: {
    // 生产构建时该变量为空，前端会回落到 Core 注入首页的 meta
    "import.meta.env.VITE_LAYOUTSEE_SESSION": JSON.stringify(process.env.VITE_LAYOUTSEE_SESSION ?? ""),
  },
  server: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: {
      "/api": proxyToCore,
      "/mcp": proxyToCore,
      "/health": proxyToCore,
    },
  },
});
