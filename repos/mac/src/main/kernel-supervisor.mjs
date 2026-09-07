import { EventEmitter } from "node:events";
import { randomBytes } from "node:crypto";
import { spawn } from "node:child_process";
import { join } from "node:path";
import { deriveSessionToken, parseReadyLine, verifyInfo } from "../shared/handshake.mjs";

const DEFAULTS = Object.freeze({
  // 15s 是 spec 预算；本机实测新 inode 首次执行会被系统安全评估拖到 8-20s，
  // 评估完成后热启动仅 ~0.3s。放宽到 25s 并自动重试一次，详见 technical-design §6.2。
  startTimeoutMs: 25_000,
  startRetryAttempts: 1,
  infoTimeoutMs: 3_000,
  stopTimeoutMs: 3_000,
  fallbackDelayMs: 750,
  fallbackPollMs: 150,
  healthIntervalMs: 2_000,
  healthFailureThreshold: 2,
  stableResetMs: 60_000,
  portStart: 33299,
  portAttempts: 11,
  restartBackoffMs: Object.freeze([1_000, 2_000, 4_000]),
});

function delay(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason);
      return;
    }
    const timer = setTimeout(resolve, milliseconds);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(signal.reason);
    }, { once: true });
  });
}

function safeDetail(detail) {
  if (typeof detail === "string") return detail;
  if (!detail || typeof detail !== "object") return null;
  return Object.freeze({
    code: typeof detail.code === "string" ? detail.code : "CORE_STATE_CHANGED",
    attempt: Number.isInteger(detail.attempt) ? detail.attempt : undefined,
    delayMs: Number.isInteger(detail.delayMs) ? detail.delayMs : undefined,
  });
}

export class KernelSupervisor extends EventEmitter {
  constructor({
    resourcesPath,
    fetchImpl = globalThis.fetch,
    spawnProcess = spawn,
    createNonce = () => randomBytes(32).toString("hex"),
    killProcessGroup = (pid, signal) => process.kill(-pid, signal),
    log = () => {},
    ...options
  }) {
    super();
    this.resourcesPath = resourcesPath;
    this.fetchImpl = fetchImpl;
    this.spawnProcess = spawnProcess;
    this.createNonce = createNonce;
    this.killProcessGroup = killProcessGroup;
    this.log = log;
    this.options = { ...DEFAULTS, ...options };
    this.child = null;
    this.origin = null;
    this.bootNonce = null;
    this.state = "idle";
    this.lastDetail = null;
    this.startPromise = null;
    this.desiredRunning = false;
    this.healthFailures = 0;
    this.restartAttempts = 0;
    this.healthTimer = null;
    this.stableTimer = null;
    this.restartTimer = null;
    this.restarting = false;
  }

  snapshot() {
    return Object.freeze({
      origin: this.origin,
      state: this.state,
      detail: this.lastDetail,
      restartAttempt: this.restartAttempts,
    });
  }

  diagnostics() {
    return Object.freeze({
      state: this.state,
      detail: this.lastDetail,
      restartAttempt: this.restartAttempts,
      hasCoreProcess: Boolean(this.child),
      origin: this.origin,
    });
  }

  setState(state, detail = null) {
    this.state = state;
    this.lastDetail = safeDetail(detail);
    const snapshot = this.snapshot();
    this.log("shell", `Core 状态：${state}${this.lastDetail ? ` (${JSON.stringify(this.lastDetail)})` : ""}`);
    this.emit("state", snapshot);
  }

  async start() {
    this.desiredRunning = true;
    this.clearRestartTimer();
    if (this.state === "ready" && this.origin) return this.origin;
    if (this.startPromise) return this.startPromise;
    this.startPromise = this.startKernel().finally(() => {
      this.startPromise = null;
    });
    return this.startPromise;
  }

  async retry() {
    await this.stop();
    this.restartAttempts = 0;
    return this.start();
  }

  async startKernel() {
    const maxAttempts = 1 + this.options.startRetryAttempts;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      if (this.child) await this.stopChild();
      this.origin = null;
      this.healthFailures = 0;
      this.setState("starting");

      const executable = join(this.resourcesPath, "core", "layoutsee-core");
      const staticDirectory = join(this.resourcesPath, "web");
      const nonce = this.createNonce();
      this.bootNonce = nonce;
      // Finder 启动的 GUI 应用看不到终端 PATH；把常见工具目录补进子进程 PATH。
      const inheritedPath = process.env.PATH ?? "/usr/bin:/bin";
      const childPath = [inheritedPath, "/opt/local/bin", "/opt/homebrew/bin", "/usr/local/bin"].join(":");
      const child = this.spawnProcess(executable, ["--static-dir", staticDirectory], {
        detached: true,
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...process.env,
          PATH: childPath,
          LANG: process.env.LANG ?? "zh_CN.UTF-8",
          LC_ALL: process.env.LC_ALL ?? "zh_CN.UTF-8",
          TMPDIR: process.env.TMPDIR ?? "/tmp",
          LAYOUTSEE_BOOT_NONCE: nonce,
          PYTHONUNBUFFERED: "1",
        },
      });
      this.child = child;
      child.stderr?.on("data", (chunk) => this.log("core", chunk.toString("utf8"), [nonce]));

      try {
        const ready = await this.readReady(child, nonce);
        this.setState("validating");
        const origin = `http://127.0.0.1:${ready.port}`;
        const info = await this.fetchInfo(origin);
        verifyInfo(ready, info);
        if (this.child !== child || !this.desiredRunning) throw new Error("CORE_START_CANCELLED");
        this.origin = origin;
        this.setState("ready");
        this.installRuntimeMonitoring(child);
        return origin;
      } catch (error) {
        const code = this.publicError(error);
        await this.stopChild();
        if (code === "CORE_READY_TIMEOUT" && attempt < maxAttempts && this.desiredRunning) {
          this.log("shell", `Core 首次启动超时，正在自动重试（第 ${attempt + 1} 次）`);
          continue;
        }
        this.setState("failed", code);
        throw error;
      }
    }
  }

  async fetchInfo(origin, signal) {
    const response = await this.fetchImpl(`${origin}/api/v1/info`, {
      headers: { Accept: "application/json" },
      signal: signal ?? AbortSignal.timeout(this.options.infoTimeoutMs),
    });
    if (!response.ok) throw new Error("CORE_INFO_UNAVAILABLE");
    return response.json();
  }

  readReady(child, nonce) {
    return new Promise((resolve, reject) => {
      let buffer = "";
      let consumedBytes = 0;
      let settled = false;
      const fallbackController = new AbortController();

      const cleanup = () => {
        clearTimeout(timeoutTimer);
        child.removeListener("error", onError);
        child.removeListener("exit", onExit);
        child.stdout?.removeListener("data", onData);
        fallbackController.abort(new Error("READY_DISCOVERY_FINISHED"));
      };
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        cleanup();
        callback(value);
      };
      const onError = (error) => finish(reject, error);
      const onExit = (code) => finish(reject, new Error(`CORE_EXITED_${code ?? "UNKNOWN"}`));
      const onData = (chunk) => {
        const text = chunk.toString("utf8");
        consumedBytes += Buffer.byteLength(text, "utf8");
        if (consumedBytes > 8192) {
          finish(reject, new Error("READY_LINE_TOO_LARGE"));
          return;
        }
        buffer += text;
        let lineEnd = buffer.indexOf("\n");
        while (lineEnd >= 0) {
          const line = buffer.slice(0, lineEnd).trimEnd();
          buffer = buffer.slice(lineEnd + 1);
          if (line.startsWith("READY ")) {
            try {
              finish(resolve, parseReadyLine(line));
            } catch (error) {
              finish(reject, error);
            }
            return;
          }
          lineEnd = buffer.indexOf("\n");
        }
      };

      const timeoutTimer = setTimeout(
        () => finish(reject, new Error("CORE_READY_TIMEOUT")),
        this.options.startTimeoutMs,
      );
      child.once("error", onError);
      child.once("exit", onExit);
      child.stdout?.on("data", onData);

      void this.discoverReadyFromInfo(child, nonce, fallbackController.signal)
        .then((ready) => finish(resolve, ready))
        .catch((error) => {
          if (!fallbackController.signal.aborted && error?.message !== "CORE_READY_FALLBACK_TIMEOUT") {
            this.log("shell", `Core READY 安全回退失败：${this.publicError(error)}`);
          }
        });
    });
  }

  async discoverReadyFromInfo(child, nonce, signal) {
    await delay(this.options.fallbackDelayMs, signal);
    while (!signal.aborted) {
      for (let offset = 0; offset < this.options.portAttempts; offset += 1) {
        const port = this.options.portStart + offset;
        try {
          const envelope = await this.fetchInfo(`http://127.0.0.1:${port}`, signal);
          const data = envelope?.data;
          if (!envelope?.ok || data?.nonce !== nonce || data?.port !== port) continue;
          const ready = parseReadyLine(`READY ${JSON.stringify(data)}`);
          verifyInfo(ready, envelope);
          if (child.exitCode !== null || this.child !== child) throw new Error("CORE_EXITED_DURING_FALLBACK");
          this.log("shell", "未收到 stdout READY，已通过本次启动身份校验完成安全回退");
          return ready;
        } catch (error) {
          if (signal.aborted) throw signal.reason;
          if (["VERSION_INCOMPATIBLE", "CORE_IDENTITY_MISMATCH"].includes(error?.message)) throw error;
        }
      }
      await delay(this.options.fallbackPollMs, signal);
    }
    throw new Error("CORE_READY_FALLBACK_TIMEOUT");
  }

  installRuntimeMonitoring(child) {
    child.once("exit", (code) => {
      if (this.child !== child || !this.desiredRunning || ["stopping", "stopped"].includes(this.state)) return;
      this.child = null;
      this.origin = null;
      void this.scheduleRestart(`CORE_EXITED_${code ?? "UNKNOWN"}`);
    });
    this.clearHealthTimer();
    this.healthTimer = setInterval(() => void this.checkHealth(), this.options.healthIntervalMs);
    clearTimeout(this.stableTimer);
    this.stableTimer = setTimeout(() => {
      this.restartAttempts = 0;
    }, this.options.stableResetMs);
  }

  async checkHealth() {
    if (this.state !== "ready" || !this.origin || !this.child) return;
    try {
      const response = await this.fetchImpl(`${this.origin}/health/ready`, {
        headers: { Accept: "application/json" },
        signal: AbortSignal.timeout(this.options.infoTimeoutMs),
      });
      if (!response.ok) throw new Error("CORE_HEALTH_UNAVAILABLE");
      this.healthFailures = 0;
    } catch {
      this.healthFailures += 1;
      if (this.healthFailures < this.options.healthFailureThreshold) return;
      this.setState("unhealthy", "CORE_HEALTH_CHECK_FAILED");
      await this.scheduleRestart("CORE_HEALTH_CHECK_FAILED");
    }
  }

  async scheduleRestart(code) {
    if (!this.desiredRunning || this.restarting) return;
    this.restarting = true;
    this.clearRuntimeTimers();
    await this.stopChild();
    if (!this.desiredRunning) {
      this.restarting = false;
      return;
    }
    const delayMs = this.options.restartBackoffMs[this.restartAttempts];
    if (delayMs === undefined) {
      this.restarting = false;
      this.setState("failed", "CORE_RESTART_BUDGET_EXHAUSTED");
      return;
    }
    this.restartAttempts += 1;
    this.setState("restarting", { code, attempt: this.restartAttempts, delayMs });
    await new Promise((resolve) => {
      this.restartTimer = setTimeout(resolve, delayMs);
    });
    this.restartTimer = null;
    this.restarting = false;
    if (!this.desiredRunning) return;
    try {
      await this.start();
    } catch {
      await this.scheduleRestart("CORE_RESTART_FAILED");
    }
  }

  publicError(error) {
    const code = error instanceof Error ? error.message : "CORE_START_FAILED";
    return /^(CORE|READY|VERSION)_/.test(code) ? code : "CORE_START_FAILED";
  }

  clearHealthTimer() {
    if (this.healthTimer) clearInterval(this.healthTimer);
    this.healthTimer = null;
  }

  clearRestartTimer() {
    if (this.restartTimer) clearTimeout(this.restartTimer);
    this.restartTimer = null;
  }

  clearRuntimeTimers() {
    this.clearHealthTimer();
    clearTimeout(this.stableTimer);
    this.stableTimer = null;
  }

  sessionToken() {
    return this.bootNonce ? deriveSessionToken(this.bootNonce) : null;
  }

  async stopChild() {
    const child = this.child;
    if (!child) return;
    this.child = null;
    this.origin = null;
    this.bootNonce = null;
    try {
      this.killProcessGroup(child.pid, "SIGTERM");
    } catch {
      child.kill("SIGTERM");
    }
    await Promise.race([
      new Promise((resolve) => child.once("exit", resolve)),
      delay(this.options.stopTimeoutMs),
    ]);
    if (child.exitCode === null) {
      try {
        this.killProcessGroup(child.pid, "SIGKILL");
      } catch {
        child.kill("SIGKILL");
      }
    }
  }

  async stop() {
    this.desiredRunning = false;
    this.restarting = false;
    this.clearRestartTimer();
    this.clearRuntimeTimers();
    this.setState("stopping");
    await this.stopChild();
    this.setState("stopped");
  }
}
