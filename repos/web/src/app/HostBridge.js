import { api, setSessionToken } from "../api/client.js";

/**
 * 宿主桥：把「Electron 壳」与「浏览器」两种宿主的差异收敛到一处。
 *
 * 规则：调用方只看 `kind` 与 `can`，不去嗅探 window.layoutSeeShell。
 * 能力为 false 时，要么这里给等效降级，要么由调用方隐藏入口，不留死按钮。
 */
const shell = typeof window !== "undefined" ? window.layoutSeeShell : null;
const isShell = Boolean(shell);
const listeners = new Set();
let latestSession = null;

// Core 托管 index.html 时会把这个占位符替换成真实令牌；vite dev 下原样保留
const SESSION_PLACEHOLDER = "__LAYOUTSEE_SESSION__";

function readInjectedSession() {
  if (typeof document === "undefined") return null;
  const value = document.querySelector('meta[name="layoutsee-session"]')?.getAttribute("content")?.trim();
  if (!value || value === SESSION_PLACEHOLDER) return null;
  return value;
}

// dev 通道：dev:web 脚本把派生令牌注入 vite define，浏览器与 Core 不同源时用它
function readDevSession() {
  const value = import.meta.env?.VITE_LAYOUTSEE_SESSION;
  return typeof value === "string" && value ? value : null;
}

function publish() {
  for (const listener of [...listeners]) listener(latestSession);
}

function prefersDark() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
}

async function browserDiagnostics() {
  const lines = [
    `host: browser`,
    `origin: ${window.location.origin}`,
    `userAgent: ${navigator.userAgent}`,
  ];
  try {
    const info = await api.info();
    // 不输出 nonce：它能派生会话令牌
    lines.push(`core: port=${info.port} pid=${info.pid} product=${info.productVersion} api=${info.apiVersion}`);
  } catch (error) {
    lines.push(`core: 不可用（${error?.code ?? "UNKNOWN"}）`);
  }
  return lines.join("\n");
}

export const HostBridge = Object.freeze({
  kind: isShell ? "shell" : "browser",

  // 壳专属能力清单：为 false 时调用方应隐藏入口或使用下面的降级实现
  can: Object.freeze({
    saveFile: isShell,
    openDirectory: isShell,
    pickAdbPath: isShell,
    nativeTheme: isShell,
    processControl: isShell,
  }),

  async init() {
    // 浏览器宿主没有 preload，令牌来自首页 meta（生产）或 vite define（开发）
    if (!isShell) {
      const token = readInjectedSession() ?? readDevSession();
      setSessionToken(token);
      latestSession = {
        state: token ? "ready" : "no_session",
        origin: typeof window !== "undefined" ? window.location.origin : "",
        sessionToken: token,
      };
      publish();
      return latestSession;
    }
    latestSession = await shell.getKernelSession().catch(() => null);
    setSessionToken(latestSession?.sessionToken ?? null);
    shell.onKernelStateChange((session) => {
      latestSession = { ...(latestSession || {}), ...session };
      setSessionToken(latestSession.sessionToken ?? null);
      publish();
    });
    return latestSession;
  },

  getSession() {
    return latestSession;
  },

  subscribe(listener) {
    listeners.add(listener);
    if (latestSession) listener(latestSession);
    return () => listeners.delete(listener);
  },

  getAppInfo: () => (isShell ? shell.getAppInfo() : Promise.resolve({ version: "web", platform: "browser", arch: "-" })),
  retryKernel: () => shell?.retryKernel(),
  quit: () => shell?.quit(),

  getSanitizedDiagnostics: () => (isShell ? shell.getSanitizedDiagnostics() : browserDiagnostics()),

  async copySanitizedDiagnostics() {
    if (isShell) return shell.copySanitizedDiagnostics();
    const text = await browserDiagnostics();
    await navigator.clipboard.writeText(text);
    return { copied: true };
  },

  // 目录类能力浏览器给不了，统一返回 opened:false，由调用方展示路径与复制按钮
  openLogsDir: () => (isShell ? shell.openLogsDir() : Promise.resolve({ opened: false })),
  openPluginsDir: () => (isShell ? shell.openPluginsDir() : Promise.resolve({ opened: false })),
  chooseAdbPath: () => (isShell ? shell.chooseAdbPath() : Promise.resolve(null)),

  exportLayout: (name, content) => (isShell ? shell.exportLayout(name, content) : Promise.resolve({ saved: false, fallback: true })),

  openTrustedExternal: (kind) => {
    if (isShell) return shell.openTrustedExternal(kind);
    // 浏览器里外链就是普通导航，交给调用方给出的 kind→URL 映射之外不做别的
    return Promise.resolve({ opened: false });
  },

  getSystemTheme: () => (isShell ? shell.getSystemTheme() : Promise.resolve(prefersDark())),
  setNativeTheme: (theme) => shell?.setNativeTheme(theme),
  onSystemThemeChange: (listener) => {
    if (isShell) return shell.onSystemThemeChange(listener);
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media?.addEventListener) return () => {};
    const handler = (event) => listener(event.matches ? "dark" : "light");
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  },
});

export const KERNEL_STATE_TEXT = Object.freeze({
  idle: "正在准备本地运行环境…",
  starting: "正在启动本地 Core…",
  validating: "正在校验 Core 身份与版本…",
  ready: "本地 Core 已就绪",
  unhealthy: "Core 暂时失去响应，正在尝试恢复…",
  restarting: "Core 正在自动恢复…",
  stopping: "正在安全退出…",
  stopped: "Core 已停止。",
  failed: "Core 启动失败，请重试或查看日志。",
  no_session: "未取得会话令牌，当前只能只读浏览。",
});
