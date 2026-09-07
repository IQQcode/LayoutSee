// 工作台交互纯函数单测：终端历史环形缓冲、高危命令识别、XPath 命中序号收敛
// 两个组件都是 JSX，这里沿用 scrcpy-stream 测试的做法：只截取纯函数片段执行
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

function loadTerminalPure() {
  const source = readFileSync(join(here, "../src/features/workbench/tabs/TerminalTab.jsx"), "utf8");
  const block = source.slice(source.indexOf("const HISTORY_LIMIT"), source.indexOf("export function TerminalTab"));
  return new Function(`${block}; return { HISTORY_LIMIT, mergeHistory, riskOf };`)();
}

function loadElementPure() {
  const source = readFileSync(join(here, "../src/features/workbench/tabs/ElementTab.jsx"), "utf8");
  const start = source.indexOf("function boundedMatchIndex");
  const block = source.slice(start, source.indexOf("\n}\n", start) + 3);
  return new Function(`${block}; return { boundedMatchIndex };`)();
}

test("终端历史置顶去重并裁到 100 条", () => {
  const { HISTORY_LIMIT, mergeHistory } = loadTerminalPure();
  assert.equal(HISTORY_LIMIT, 100);

  let history = [];
  for (let index = 0; index < 120; index += 1) history = mergeHistory(history, `cmd-${index}`);
  assert.equal(history.length, 100);
  assert.equal(history[0], "cmd-119", "最新命令排在最前");
  assert.equal(history.at(-1), "cmd-20", "超出上限的最旧命令被丢弃");

  const deduped = mergeHistory(["a", "b", "c"], "b");
  assert.deepEqual(deduped, ["b", "a", "c"], "重复命令上浮而不是产生两条");
});

test("高危命令被识别，普通命令放行", () => {
  const { riskOf } = loadTerminalPure();
  for (const command of ["rm -rf /sdcard/x", "pm uninstall com.demo", "PM CLEAR com.demo", "reboot", "settings put system x 1", "am force-stop com.demo", "dd if=/dev/zero of=/sdcard/x"]) {
    assert.ok(riskOf(command), `应识别为高危：${command}`);
  }
  for (const command of ["getprop ro.product.model", "dumpsys battery", "ls -al /sdcard", "pm list packages -3"]) {
    assert.equal(riskOf(command), null, `不应误判为高危：${command}`);
  }
});

test("XPath 命中序号越界收敛", () => {
  const { boundedMatchIndex } = loadElementPure();
  assert.equal(boundedMatchIndex(0, 0), -1, "空命中集合不定位任何节点");
  assert.equal(boundedMatchIndex(-5, 3), 0);
  assert.equal(boundedMatchIndex(9, 3), 2);
  assert.equal(boundedMatchIndex(1, 3), 1);
});
