// 日志桥：把统一日志的上报通道接到 Core /api/v1/ui-logs，应用启动时装配一次。
import { api } from "../api/client.js";
import { configureUiLogUploader } from "../api/logger.js";

let wired = false;

export function wireLogging() {
  if (wired) return;
  wired = true;
  configureUiLogUploader((entries) => api.uiLogs({ entries }));
}
