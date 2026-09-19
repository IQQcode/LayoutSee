import assert from "node:assert/strict";
import test from "node:test";
import { deriveSessionToken, parseReadyLine, verifyInfo } from "../src/shared/handshake.mjs";

const nonce = "a".repeat(64);
const readyValue = Object.freeze({
  port: 11663,
  pid: 1234,
  nonce,
  productVersion: "22.6.1",
  apiVersion: "1.0",
  snapshotSchemaVersion: "1.0",
});

test("严格解析合法 READY 行并校验 info 身份", () => {
  const ready = parseReadyLine(`READY ${JSON.stringify(readyValue)}`);
  const info = verifyInfo(ready, { ok: true, data: readyValue, requestId: "req-test-0001" });
  assert.deepEqual(info, readyValue);
});

test("拒绝错误 nonce、超长 READY 与版本不兼容", () => {
  assert.throws(() => parseReadyLine(`READY ${JSON.stringify({ ...readyValue, nonce: "bad" })}`), /READY_NONCE_INVALID/);
  assert.throws(() => parseReadyLine(`READY ${"x".repeat(8193)}`), /READY_LINE_TOO_LARGE/);
  assert.throws(() => parseReadyLine(`READY ${JSON.stringify({ ...readyValue, apiVersion: "2.0" })}`), /VERSION_INCOMPATIBLE/);
});

test("拒绝 READY 与 info 进程身份不一致", () => {
  assert.throws(
    () => verifyInfo(readyValue, { ok: true, data: { ...readyValue, pid: 9999 }, requestId: "req-test-0002" }),
    /CORE_IDENTITY_MISMATCH/,
  );
});

test("会话令牌由 nonce 确定性派生且拒绝非法 nonce", () => {
  const token = deriveSessionToken(nonce);
  assert.match(token, /^[a-f0-9]{64}$/);
  assert.equal(token, deriveSessionToken(nonce));
  assert.notEqual(token, deriveSessionToken("b".repeat(64)));
  assert.throws(() => deriveSessionToken("short"), /READY_NONCE_INVALID/);
});

test("会话令牌与 Core 侧金样值一致", () => {
  assert.equal(deriveSessionToken("a".repeat(64)), "a8151948d84f365c4722324e732be43b0e0a5e2558fc07a22b1e0057abb1ee77");
});
