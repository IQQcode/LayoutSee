// 平台分支纯函数单测：工作台可见 Tab 计算、设备页平台过滤
// 两个组件都是 JSX，沿用 workbench-interactions.test.mjs 的做法：只截取纯函数片段执行
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

function loadWorkbenchPure() {
  const source = readFileSync(join(here, "../src/features/workbench/WorkbenchPage.jsx"), "utf8");
  const start = source.indexOf("const TAB_IDS");
  const fnStart = source.indexOf("function visibleTabs");
  const block = source.slice(start, source.indexOf("\n}\n", fnStart) + 3);
  return new Function(`${block}; return { TAB_IDS, visibleTabs };`)();
}

function loadDevicesPure() {
  const source = readFileSync(join(here, "../src/features/devices/DevicesPage.jsx"), "utf8");
  const start = source.indexOf("const PLATFORM_LABELS");
  const fnStart = source.indexOf("function devicesForPlatform");
  const block = source.slice(start, source.indexOf("\n}\n", fnStart) + 3);
  return new Function(`${block}; return { PLATFORM_LABELS, devicesForPlatform };`)();
}

test("iOS 工作台隐藏常用 Tab，Android 保持五 Tab", () => {
  const { TAB_IDS, visibleTabs } = loadWorkbenchPure();
  assert.deepEqual(visibleTabs("ios"), ["element", "mcp", "plugins", "intelligence"]);
  assert.equal(visibleTabs("ios").includes("common"), false);
  assert.deepEqual(visibleTabs("android"), TAB_IDS);
  assert.deepEqual(visibleTabs(undefined), TAB_IDS, "平台未知（设备未加载）时按 Android 处理");
});

test("设备页按平台过滤设备列表，互不混排", () => {
  const { devicesForPlatform } = loadDevicesPure();
  const devices = [
    { deviceId: "android-1", platform: "android" },
    { deviceId: "ios-1", platform: "ios" },
    { deviceId: "android-2", platform: "android" },
  ];
  assert.deepEqual(devicesForPlatform(devices, "android").map((item) => item.deviceId), ["android-1", "android-2"]);
  assert.deepEqual(devicesForPlatform(devices, "ios").map((item) => item.deviceId), ["ios-1"]);
  assert.deepEqual(devicesForPlatform(devices, "harmony"), []);
  assert.deepEqual(devicesForPlatform(null, "android"), [], "设备列表未加载时返回空数组");
});

test("平台展示名映射覆盖契约里的两种平台", () => {
  const { PLATFORM_LABELS } = loadDevicesPure();
  assert.equal(PLATFORM_LABELS.android, "Android");
  assert.equal(PLATFORM_LABELS.ios, "iOS");
});
