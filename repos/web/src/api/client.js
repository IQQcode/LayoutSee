import { LogTags, uiLog } from "./logger.js";

const JSON_HEADERS = Object.freeze({
  Accept: "application/json",
  "Content-Type": "application/json",
});

// 上报通道自身不参与网络日志，避免递归
const LOG_EXEMPT_PATHS = new Set(["/api/v1/ui-logs"]);

let sessionToken = null;

export function setSessionToken(token) {
  sessionToken = token || null;
}

export function getSessionToken() {
  return sessionToken;
}

export class ApiError extends Error {
  constructor(code, message, options = {}) {
    super(message || "请求失败");
    this.name = "ApiError";
    this.code = code || "CORE_UNAVAILABLE";
    this.retryable = Boolean(options.retryable);
    this.status = options.status || 0;
    this.details = options.details || null;
  }
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok || payload?.ok === false) {
    const error = payload?.error || {};
    throw new ApiError(error.code || `HTTP_${response.status}`, error.message || `请求失败（${response.status}）`, {
      retryable: error.retryable,
      status: response.status,
      details: error.details,
    });
  }
  return payload?.ok === true ? payload.data : payload;
}

export async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeout ?? 10_000);
  const method = (options.method || "GET").toUpperCase();
  const started = performance.now();
  try {
    const response = await fetch(path, {
      ...options,
      headers: {
        ...JSON_HEADERS,
        ...(sessionToken && !options.anonymous ? { "X-LayoutSee-Session": sessionToken } : {}),
        ...(options.headers || {}),
      },
      body: options.body === undefined || typeof options.body === "string" ? options.body : JSON.stringify(options.body),
      signal: options.signal || controller.signal,
    });
    if (!LOG_EXEMPT_PATHS.has(path)) {
      const durationMs = Math.round(performance.now() - started);
      if (!response.ok) {
        // 关键路径观测：任何非 2xx 都带 method+path+status 落盘
        uiLog(LogTags.network, `${method} ${path} → HTTP ${response.status}`, "error", `${durationMs}ms`);
      } else if (method !== "GET" || durationMs > 5_000) {
        uiLog(LogTags.network, `${method} ${path} → ${response.status}`, "info", `${durationMs}ms`);
      }
    }
    return await parseResponse(response);
  } catch (error) {
    if (!LOG_EXEMPT_PATHS.has(path) && !(error instanceof ApiError && error.code === "OPERATION_TIMEOUT" && error.status === 0)) {
      uiLog(LogTags.network, `${method} ${path} 异常`, "error", error?.message ?? String(error));
    }
    if (error instanceof ApiError) throw error;
    if (error?.name === "AbortError") throw new ApiError("OPERATION_TIMEOUT", "操作超时，已保留当前可用内容。", { retryable: true });
    throw new ApiError("CORE_UNAVAILABLE", "本地 Core 暂时不可用。", { retryable: true });
  } finally {
    window.clearTimeout(timeout);
  }
}

export const api = Object.freeze({
  info: () => request("/api/v1/info"),
  devices: () => request("/api/v1/devices"),
  refreshDevices: () => request("/api/v1/devices/refresh", { method: "POST" }),
  deviceDiagnostics: (deviceId) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/diagnostics`),
  currentApp: (deviceId) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/current-app`),
  apps: (deviceId, query = "", includeSystem = false) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/apps?q=${encodeURIComponent(query)}&includeSystem=${includeSystem ? "true" : "false"}`, { timeout: 15_000 }),
  deviceScreenshot: (deviceId) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/screenshot`, { timeout: 15_000 }),
  windowSize: (deviceId) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/window-size`, { timeout: 8_000 }),
  // logcat 增量读取：after 传上一次响应的 cursor，Core 只回新行
  logcat: (deviceId, after = null, limit = 500) => request(
    `/api/v1/devices/${encodeURIComponent(deviceId)}/logcat?limit=${Number(limit) || 500}${after == null ? "" : `&after=${Number(after)}`}`,
    { timeout: 25_000 },
  ),
  clearLogcat: (deviceId, options = {}) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/logcat/clear`, {
    method: "POST",
    body: { actionId: crypto.randomUUID(), source: "ui", ...options },
  }),
  mediaCapabilities: (deviceId) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/media/capabilities`),
  action: (deviceId, action) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/actions`, {
    method: "POST",
    body: { actionId: crypto.randomUUID(), source: "ui", ...action },
  }),
  shell: (deviceId, command, timeoutMs = 15_000) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/shell`, {
    method: "POST",
    body: { actionId: crypto.randomUUID(), source: "ui", command, timeoutMs },
    // 前端超时比 Core 的执行上限多留 5s，避免请求先断而设备命令仍在跑
    timeout: timeoutMs + 5_000,
  }),
  capture: (deviceId) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/snapshots`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: {},
    timeout: 20_000,
  }),
  latestSnapshot: (deviceId) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/snapshots/latest`),
  snapshot: (snapshotId) => request(`/api/v1/snapshots/${encodeURIComponent(snapshotId)}`),
  xpath: (snapshotId, expression) => request(`/api/v1/snapshots/${encodeURIComponent(snapshotId)}/xpath`, { method: "POST", body: { expression } }),
  selectors: (snapshotId, nodeKey) => request(`/api/v1/snapshots/${encodeURIComponent(snapshotId)}/selectors`, { method: "POST", body: { nodeKey } }),
  summary: (snapshotId) => request(`/api/v1/snapshots/${encodeURIComponent(snapshotId)}/summary`, { method: "POST", body: {} }),
  layoutDiagnostics: (snapshotId) => request(`/api/v1/snapshots/${encodeURIComponent(snapshotId)}/diagnostics`, { method: "POST", body: {} }),
  settings: () => request("/api/v1/settings"),
  paths: () => request("/api/v1/paths"),
  saveSettings: (settings) => request("/api/v1/settings", { method: "PUT", body: settings }),
  setReadonly: (deviceId, readonly) => request(`/api/v1/devices/${encodeURIComponent(deviceId)}/readonly`, { method: "PUT", body: { readonly } }),
  plugins: () => request("/api/v1/plugins"),
  pluginIndex: (refresh = false) => request(`/api/v1/plugins/index${refresh ? "?refresh=true" : ""}`),
  reloadPlugins: () => request("/api/v1/plugins/reload", { method: "POST", body: {} }),
  mcpTools: () => request("/api/v1/mcp/tools"),
  // 插件桥的工具调用复用 MCP JSON-RPC 端点，错误映射回 ApiError 以便统一提示
  callTool: async (deviceId, name, args = {}) => {
    const payload = await request(`/mcp/${encodeURIComponent(deviceId)}/message`, {
      method: "POST",
      body: { jsonrpc: "2.0", id: crypto.randomUUID(), method: "tools/call", params: { name, arguments: args } },
      timeout: 20_000,
    });
    if (payload?.error) throw new ApiError("CORE_UNAVAILABLE", payload.error.message || "工具调用失败");
    const text = payload?.result?.content?.[0]?.text;
    let parsed = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }
    if (payload?.result?.isError) {
      const error = parsed?.error ?? {};
      throw new ApiError(error.code, error.message, { retryable: error.retryable, details: error.details });
    }
    return parsed;
  },
  uiLogs: (entries) => request("/api/v1/ui-logs", { method: "POST", body: entries, timeout: 5_000 }),
});

export function normalizeList(value, key) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.[key])) return value[key];
  if (Array.isArray(value?.items)) return value.items;
  return [];
}

export function errorMessage(error) {
  return error instanceof ApiError ? error.message : "发生未知错误，请重试。";
}
