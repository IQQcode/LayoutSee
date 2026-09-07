import test from "node:test";
import assert from "node:assert/strict";

import { buildExtensionModel, isPluginTab, pluginAssetUrl, pluginTabKey } from "../src/features/plugins/registry.js";

const logcatEntry = {
  id: "android-logcat",
  name: "Android日志抓取",
  version: "1.0.0",
  origin: "builtin",
  status: "ready",
  activation: "onOpen",
  hosts: ["app"],
  devicePlatforms: ["android"],
  permissions: ["device.read", "device.write"],
  contributions: { workbenchTabs: [{ id: "logcat", title: "日志抓取", entry: "index.html", order: 300 }] },
};

const overviewEntry = {
  id: "snapshot-overview",
  name: "快照概览",
  version: "1.0.0",
  origin: "builtin",
  status: "ready",
  hosts: ["app", "web"],
  devicePlatforms: ["android"],
  contributions: { workbenchTabs: [{ id: "overview", title: "概览", entry: "index.html", order: 700 }] },
};

const index = { items: [overviewEntry, logcatEntry] };

test("app 宿主下日志插件出现在入口列表并按 order 排序", () => {
  const model = buildExtensionModel(index, { host: "app", devicePlatform: "android" });
  assert.deepEqual(model.tabs.map((tab) => tab.pluginId), ["android-logcat", "snapshot-overview"]);
  const [logcat] = model.tabs;
  assert.equal(logcat.key, pluginTabKey("android-logcat", "logcat"));
  assert.equal(logcat.url, pluginAssetUrl("android-logcat", "index.html"));
  assert.ok(isPluginTab(logcat.key));
  assert.equal(model.unavailable.length, 0);
});

test("web 宿主下只声明 app 的插件被过滤且说明原因", () => {
  const model = buildExtensionModel(index, { host: "web", devicePlatform: "android" });
  assert.deepEqual(model.tabs.map((tab) => tab.pluginId), ["snapshot-overview"]);
  assert.deepEqual(model.unavailable.map((item) => [item.pluginId, item.reason]), [["android-logcat", "host-mismatch"]]);
});

test("设备平台不匹配同样进 unavailable 而不是静默丢弃", () => {
  const model = buildExtensionModel({ items: [logcatEntry] }, { host: "app", devicePlatform: "ios" });
  assert.equal(model.tabs.length, 0);
  assert.equal(model.unavailable[0].reason, "device-mismatch");
});
