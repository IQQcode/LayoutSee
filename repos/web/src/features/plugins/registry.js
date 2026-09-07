import { HostBridge } from "../../app/HostBridge.js";

/**
 * 扩展模型：把 Core 的插件索引翻译成「当前宿主 + 当前设备平台」下可渲染的贡献点。
 *
 * Core 不做 host / devicePlatform 过滤（同一个 Core 同时服务壳与浏览器），
 * 因此过滤责任在这里；被过滤掉的插件不丢弃，进 unavailable 供插件页解释原因。
 */

export const PLUGIN_TAB_PREFIX = "plugin.";

export function currentHost() {
  return HostBridge.kind === "shell" ? "app" : "web";
}

export function pluginAssetUrl(pluginId, relative) {
  const path = String(relative || "").split("/").filter(Boolean).map(encodeURIComponent).join("/");
  return `/plugin-assets/${encodeURIComponent(pluginId)}/${path}`;
}

export function pluginTabKey(pluginId, tabId) {
  return `${PLUGIN_TAB_PREFIX}${pluginId}.${tabId}`;
}

export function isPluginTab(key) {
  return typeof key === "string" && key.startsWith(PLUGIN_TAB_PREFIX);
}

const UNAVAILABLE_TEXT = Object.freeze({
  "host-mismatch": "该插件未声明支持当前宿主",
  "device-mismatch": "该插件不支持当前设备平台",
  incompatible: "插件要求的 LayoutSee 版本与当前不匹配",
  invalid: "插件清单无效",
});

function contribution(entry, key) {
  const block = entry?.contributions?.[key];
  return Array.isArray(block) ? block : [];
}

export function buildExtensionModel(index, options = {}) {
  const host = options.host || currentHost();
  const devicePlatform = options.devicePlatform || "android";
  const tabs = [];
  const cards = [];
  const commands = [];
  const unavailable = [];

  for (const entry of index?.items ?? []) {
    const base = { pluginId: entry.id, pluginName: entry.name, version: entry.version };
    if (entry.status !== "ready") {
      unavailable.push({ ...base, reason: entry.status, message: entry.error?.message || UNAVAILABLE_TEXT[entry.status] || "插件不可用" });
      continue;
    }
    if (!(entry.hosts ?? []).includes(host)) {
      unavailable.push({ ...base, reason: "host-mismatch", message: UNAVAILABLE_TEXT["host-mismatch"] });
      continue;
    }
    if (!(entry.devicePlatforms ?? []).includes(devicePlatform)) {
      unavailable.push({ ...base, reason: "device-mismatch", message: UNAVAILABLE_TEXT["device-mismatch"] });
      continue;
    }
    const shared = { ...base, activation: entry.activation || "onOpen", permissions: entry.permissions ?? [], origin: entry.origin };
    for (const tab of contribution(entry, "workbenchTabs")) {
      tabs.push({ ...shared, key: pluginTabKey(entry.id, tab.id), id: tab.id, title: tab.title, order: tab.order ?? 500, url: pluginAssetUrl(entry.id, tab.entry) });
    }
    for (const card of contribution(entry, "workbenchCards")) {
      cards.push({ ...shared, key: `${entry.id}.${card.id}`, id: card.id, slot: card.slot, height: card.height ?? 220, url: pluginAssetUrl(entry.id, card.entry) });
    }
    for (const command of contribution(entry, "commands")) {
      commands.push({ ...shared, key: `${entry.id}.${command.id}`, id: command.id, title: command.title });
    }
  }

  tabs.sort((left, right) => left.order - right.order || left.key.localeCompare(right.key));
  return { tabs, cards, commands, unavailable };
}

export const EMPTY_EXTENSIONS = Object.freeze({ tabs: [], cards: [], commands: [], unavailable: [] });

export function cardsForSlot(model, slot) {
  return (model?.cards ?? []).filter((card) => card.slot === slot);
}

export function findPluginTab(model, key) {
  return (model?.tabs ?? []).find((tab) => tab.key === key) ?? null;
}
