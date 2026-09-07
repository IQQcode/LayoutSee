// 前端统一日志：控制台输出 + 批量上报 Core 落盘（logs/ui-YYYY-MM-DD.log）。
// 统一 Tag 形如 [LayoutSee][元素查看]，用户可直接复制日志目录内容排查问题。
// 上报通道由 LoggingBridge 注入，避免与 api/client.js 相互依赖。
const PREFIX = "LayoutSee";
const MAX_BUFFER = 400;
const FLUSH_DELAY_MS = 1500;
const FLUSH_BATCH = 100;

export const LogTags = Object.freeze({
  workbench: "工作台",
  common: "常用",
  element: "元素查看",
  mcp: "MCP",
  intelligence: "布局智能",
  media: "投屏",
  devices: "设备",
  network: "网络",
  settings: "设置",
});

let upload = null;
let buffer = [];
let flushTimer = 0;
let consecutiveFailures = 0;

export function configureUiLogUploader(fn) {
  upload = typeof fn === "function" ? fn : null;
}

function flush() {
  flushTimer = 0;
  if (buffer.length === 0 || !upload || consecutiveFailures >= 3) return;
  const batch = buffer.splice(0, FLUSH_BATCH).map((entry) => ({ ...entry }));
  upload(batch)
    .then(() => {
      consecutiveFailures = 0;
      if (buffer.length > 0) schedule();
    })
    .catch(() => {
      consecutiveFailures += 1;
    });
}

function schedule() {
  if (!flushTimer) flushTimer = setTimeout(flush, FLUSH_DELAY_MS);
}

export function uiLog(tag, message, level = "info", detail) {
  const entry = {
    tag: `[${PREFIX}][${tag}]`,
    level: level === "warning" ? "warning" : level === "error" ? "error" : "info",
    message: detail === undefined ? String(message) : `${message} ${typeof detail === "string" ? detail : safeJson(detail)}`,
    timestampMs: Date.now(),
  };
  buffer.push(entry);
  if (buffer.length > MAX_BUFFER) buffer.splice(0, buffer.length - MAX_BUFFER);
  const line = `${entry.tag} ${entry.message}`;
  if (entry.level === "error") console.error(line);
  else if (entry.level === "warning") console.warn(line);
  else console.info(line);
  schedule();
}

function safeJson(value) {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

// 计时包装：记录 API 调用耗时与失败
export async function uiLogApi(tag, name, run) {
  const started = performance.now();
  try {
    const result = await run();
    uiLog(tag, `${name} 完成`, "info", `${Math.round(performance.now() - started)}ms`);
    return result;
  } catch (error) {
    uiLog(tag, `${name} 失败`, "error", `${error?.code ?? ""} ${error?.message ?? error}`);
    throw error;
  }
}
