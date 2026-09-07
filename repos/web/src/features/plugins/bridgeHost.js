import { api } from "../../api/client.js";
import { HostBridge } from "../../app/HostBridge.js";
import { LogTags, uiLog } from "../../api/logger.js";

/**
 * 插件桥宿主端：唯一的能力出口。
 *
 * 安全前提：
 * 1) iframe 是 sandbox="allow-scripts"（无 allow-same-origin），插件文档是 opaque origin，
 *    所以来源校验只能靠 event.source === frame.contentWindow，同时要求 event.origin 为 "null"。
 * 2) 插件页 CSP 是 connect-src 'none'，插件自己发不出请求；宿主也因此不向插件下发会话令牌
 *    （令牌一旦进入插件上下文就等于绕过桥，得不偿失）。
 * 3) 方法白名单 + 权限校验 + 限流三层，任何未列出的 method 直接拒绝。
 */

const PROTOCOL_VERSION = 1;
const WINDOW_MS = 1000;
const READ_QUOTA = 20;
const WRITE_QUOTA = 2;
const MAX_STORAGE_BYTES = 32 * 1024;
const GRANT_KEY = "layoutsee.pluginGrants";

const PERMISSION_OF = Object.freeze({
  "host.getContext": null,
  "ui.toast": null,
  "ui.confirm": null,
  "snapshot.get": "snapshot.read",
  "snapshot.query": "snapshot.read",
  "device.info": "device.read",
  "device.currentApp": "device.read",
  "device.logcat": "device.read",
  "device.tap": "device.write",
  "device.swipe": "device.write",
  "device.inputText": "device.write",
  "device.logcatClear": "device.write",
  "mcp.callTool": "mcp.call",
  "storage.get": "storage.local",
  "storage.set": "storage.local",
  "host.saveFile": "host.integration",
  "host.copyText": "host.integration",
});

const WRITE_METHODS = new Set(["device.tap", "device.swipe", "device.inputText", "device.logcatClear", "mcp.callTool"]);

class BridgeError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function readGrants() {
  try {
    const parsed = JSON.parse(localStorage.getItem(GRANT_KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function grantedPermissions(pluginId) {
  const value = readGrants()[pluginId];
  return Array.isArray(value) ? value : [];
}

export function setGrantedPermissions(pluginId, permissions) {
  const grants = readGrants();
  grants[pluginId] = [...new Set(permissions)];
  localStorage.setItem(GRANT_KEY, JSON.stringify(grants));
}

/** 创建一个绑定到具体 iframe 的桥会话；返回 detach。 */
export function attachBridge(frame, options) {
  const { tab, getContext, onToast, requestPermission } = options;
  const counters = { read: [], write: [] };

  const withinQuota = (bucket, quota) => {
    const now = performance.now();
    counters[bucket] = counters[bucket].filter((stamp) => now - stamp < WINDOW_MS);
    if (counters[bucket].length >= quota) return false;
    counters[bucket].push(now);
    return true;
  };

  async function ensurePermission(method) {
    const permission = PERMISSION_OF[method];
    if (!permission) return;
    if (!(tab.permissions ?? []).includes(permission)) {
      throw new BridgeError("PLUGIN_PERMISSION_DENIED", `插件未在清单声明 ${permission} 权限。`);
    }
    if (grantedPermissions(tab.pluginId).includes(permission)) return;
    const approved = await requestPermission?.(permission);
    if (!approved) throw new BridgeError("PLUGIN_PERMISSION_DENIED", `用户拒绝了 ${permission} 权限。`);
    setGrantedPermissions(tab.pluginId, [...grantedPermissions(tab.pluginId), permission]);
  }

  async function dispatch(method, params) {
    const context = getContext();
    if (!(method in PERMISSION_OF)) throw new BridgeError("INVALID_ARGUMENT", `不支持的桥方法：${method}`);
    if (!withinQuota(WRITE_METHODS.has(method) ? "write" : "read", WRITE_METHODS.has(method) ? WRITE_QUOTA : READ_QUOTA)) {
      throw new BridgeError("PLUGIN_RATE_LIMITED", "插件调用过于频繁，已限流。");
    }
    await ensurePermission(method);
    const deviceId = context.deviceId;
    switch (method) {
      case "host.getContext":
        return {
          host: HostBridge.kind === "shell" ? "app" : "web",
          deviceId,
          snapshotId: context.snapshotMeta?.snapshotId ?? null,
          readonly: Boolean(context.readonly),
          pluginId: tab.pluginId,
          theme: context.theme ?? "light",
          // 能力查询取代环境嗅探：插件按 capabilities 决定是否展示入口，不去猜宿主
          capabilities: { saveFile: HostBridge.can.saveFile, copyText: true, openDirectory: HostBridge.can.openDirectory },
        };
      case "snapshot.get":
        return context.snapshotData ?? (await api.latestSnapshot(deviceId).then((meta) => (meta.snapshotId ? api.snapshot(meta.snapshotId) : null)));
      case "snapshot.query": {
        const snapshotId = context.snapshotMeta?.snapshotId;
        if (!snapshotId) throw new BridgeError("SNAPSHOT_STALE", "当前没有可用快照。");
        return api.xpath(snapshotId, String(params?.expression ?? ""));
      }
      case "device.info":
        return api.windowSize(deviceId);
      case "device.currentApp":
        return api.currentApp(deviceId);
      case "device.logcat":
        return api.logcat(deviceId, params?.after, params?.limit);
      case "device.logcatClear":
        return api.clearLogcat(deviceId, { source: "plugin", pluginId: tab.pluginId });
      case "device.tap":
        return api.action(deviceId, { type: "tap", source: "plugin", pluginId: tab.pluginId, x: Number(params?.x), y: Number(params?.y) });
      case "device.swipe":
        return api.action(deviceId, { type: "swipe", source: "plugin", pluginId: tab.pluginId, fromX: Number(params?.fromX), fromY: Number(params?.fromY), toX: Number(params?.toX), toY: Number(params?.toY) });
      case "device.inputText":
        return api.action(deviceId, { type: "input_text", source: "plugin", pluginId: tab.pluginId, text: String(params?.text ?? "") });
      case "mcp.callTool":
        return api.callTool(deviceId, String(params?.name ?? ""), params?.arguments ?? {});
      case "storage.get":
        return { value: localStorage.getItem(`layoutsee.plugin.${tab.pluginId}.${String(params?.key ?? "")}`) };
      case "storage.set": {
        const value = String(params?.value ?? "");
        if (value.length > MAX_STORAGE_BYTES) throw new BridgeError("INVALID_ARGUMENT", "插件存储单键上限 32KB。");
        localStorage.setItem(`layoutsee.plugin.${tab.pluginId}.${String(params?.key ?? "")}`, value);
        return { saved: true };
      }
      case "host.saveFile": {
        const result = await HostBridge.exportLayout(String(params?.name ?? "plugin.txt"), String(params?.content ?? ""));
        if (result?.saved === false) throw new BridgeError("HOST_CAPABILITY_UNAVAILABLE", "当前宿主不支持保存文件，请改用复制。");
        return result;
      }
      case "host.copyText":
        await navigator.clipboard.writeText(String(params?.text ?? ""));
        return { copied: true };
      case "ui.toast":
        onToast?.(`${tab.pluginName}：${String(params?.message ?? "")}`.slice(0, 120), params?.tone === "danger" ? "danger" : "info");
        return { shown: true };
      case "ui.confirm":
        return { confirmed: window.confirm(`${tab.pluginName} 请求确认：${String(params?.message ?? "")}`) };
      default:
        throw new BridgeError("INVALID_ARGUMENT", `不支持的桥方法：${method}`);
    }
  }

  const listener = async (event) => {
    if (event.source !== frame.contentWindow || event.origin !== "null") return;
    const message = event.data;
    if (!message || message.v !== PROTOCOL_VERSION || message.kind !== "call" || typeof message.id !== "string") return;
    const reply = (payload) => frame.contentWindow?.postMessage({ v: PROTOCOL_VERSION, id: message.id, ...payload }, "*");
    try {
      reply({ kind: "result", result: await dispatch(String(message.method ?? ""), message.params) });
    } catch (error) {
      const code = error instanceof BridgeError ? error.code : error?.code || "CORE_UNAVAILABLE";
      uiLog(LogTags.workbench, `插件桥调用失败 ${tab.pluginId}.${message.method}`, "warning", `${code} ${error?.message ?? ""}`);
      reply({ kind: "error", error: { code, message: error?.message ?? "插件调用失败", retryable: Boolean(error?.retryable) } });
    }
  };

  window.addEventListener("message", listener);
  return () => window.removeEventListener("message", listener);
}

/** 宿主主动推事件（快照更新、节点选中）给插件。 */
export function postBridgeEvent(frame, name, payload) {
  frame?.contentWindow?.postMessage({ v: PROTOCOL_VERSION, kind: "event", method: name, params: payload }, "*");
}
