import assert from "node:assert/strict";
import test from "node:test";
import { EventEmitter } from "node:events";
import { KernelSupervisor } from "../src/main/kernel-supervisor.mjs";

const nonce = "a".repeat(64);
const readyValue = {
  port: 33299,
  pid: 4242,
  nonce,
  productVersion: "0.1.0",
  apiVersion: "1.0",
  snapshotSchemaVersion: "1.0",
};

class FakeChild extends EventEmitter {
  constructor() {
    super();
    this.stdout = new EventEmitter();
    this.stderr = new EventEmitter();
    this.pid = 4242;
    this.exitCode = null;
  }

  emitReady() {
    this.stdout.emit("data", Buffer.from(`READY ${JSON.stringify(readyValue)}\n`));
  }
}

function makeSupervisor({ children, timeoutMs = 200, attempts = 1 }) {
  const queue = [...children];
  let spawnCount = 0;
  const supervisor = new KernelSupervisor({
    resourcesPath: "/nonexistent",
    createNonce: () => nonce,
    killProcessGroup: () => {},
    spawnProcess: () => {
      spawnCount += 1;
      return queue.shift() ?? new FakeChild();
    },
    fetchImpl: async (url) => {
      if (!url.endsWith("/api/v1/info")) throw new Error("CORE_INFO_UNAVAILABLE");
      return { ok: true, json: async () => ({ ok: true, data: readyValue, requestId: "req-test" }) };
    },
    startTimeoutMs: timeoutMs,
    startRetryAttempts: attempts,
    stopTimeoutMs: 300,
    infoTimeoutMs: 100,
    fallbackDelayMs: 600_000,
    healthIntervalMs: 600_000,
    stableResetMs: 600_000,
    log: () => {},
  });
  return { supervisor, spawnCount: () => spawnCount };
}

test("首次 READY 超时后自动重试并成功进入 ready", async () => {
  const silent = new FakeChild();
  const readyChild = new FakeChild();
  const { supervisor, spawnCount } = makeSupervisor({ children: [silent, readyChild], attempts: 1 });
  const readyTimer = setInterval(() => readyChild.emitReady(), 50);
  try {
    const origin = await supervisor.start();
    assert.equal(origin, "http://127.0.0.1:33299");
    assert.equal(spawnCount(), 2);
    assert.equal(supervisor.state, "ready");
    assert.match(supervisor.sessionToken(), /^[a-f0-9]{64}$/);
  } finally {
    clearInterval(readyTimer);
    await supervisor.stop();
  }
});

test("两次超时耗尽重试预算后进入 failed", async () => {
  const { supervisor, spawnCount } = makeSupervisor({ children: [new FakeChild(), new FakeChild()], attempts: 1 });
  await assert.rejects(() => supervisor.start(), /CORE_READY_TIMEOUT/);
  assert.equal(spawnCount(), 2);
  assert.equal(supervisor.state, "failed");
  await supervisor.stop();
});

test("首次即就绪时不重试", async () => {
  const child = new FakeChild();
  const { supervisor, spawnCount } = makeSupervisor({ children: [child], attempts: 1 });
  setTimeout(() => child.emitReady(), 10);
  await supervisor.start();
  assert.equal(spawnCount(), 1);
  await supervisor.stop();
});
