#!/usr/bin/env node
/**
 * 浏览器宿主的一键联调入口：拉起 Core，派生会话令牌，再带着令牌与代理配置启动 vite。
 *
 * 解决两件事：
 * 1. vite dev server 不托管 API，`/api/**` 直接 404，必须代理到 Core；
 * 2. 浏览器宿主没有 preload，令牌正常由 Core 注入 index.html，但 dev 下首页来自 vite，
 *    只能通过 VITE_LAYOUTSEE_SESSION 注入。
 */
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { deriveSessionToken, parseReadyLine } from "../repos/mac/src/shared/handshake.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const READY_TIMEOUT_MS = 25_000;

const children = new Set();
let shuttingDown = false;

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) child.kill("SIGTERM");
  }
  setTimeout(() => process.exit(code), 300);
}

function track(child) {
  children.add(child);
  child.on("exit", (exitCode, signal) => {
    children.delete(child);
    if (!shuttingDown) {
      console.error(`[dev:web] 子进程退出（code=${exitCode} signal=${signal}），一并停止其余进程`);
      shutdown(exitCode ?? 1);
    }
  });
  return child;
}

async function startCore(nonce) {
  const core = track(spawn(
    "uv",
    ["run", "--project", "repos/core", "python", "-m", "layoutsee_core", "--nonce", nonce],
    { cwd: ROOT, stdio: ["ignore", "pipe", "inherit"] },
  ));
  const reader = createInterface({ input: core.stdout });
  const ready = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("CORE_READY_TIMEOUT")), READY_TIMEOUT_MS);
    reader.on("line", (line) => {
      if (!line.startsWith("READY ")) {
        console.log(`[core] ${line}`);
        return;
      }
      clearTimeout(timer);
      try {
        resolve(parseReadyLine(line));
      } catch (error) {
        reject(error);
      }
    });
    core.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`CORE_EXITED_${code}`));
    });
  });
  reader.on("line", (line) => console.log(`[core] ${line}`));
  return ready;
}

function startVite(ready) {
  const sessionToken = deriveSessionToken(ready.nonce);
  return track(spawn(
    "npm",
    ["--workspace", "@layoutsee/web", "run", "dev"],
    {
      cwd: ROOT,
      stdio: "inherit",
      env: { ...process.env, LAYOUTSEE_CORE_PORT: String(ready.port), VITE_LAYOUTSEE_SESSION: sessionToken },
    },
  ));
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

const nonce = randomBytes(32).toString("hex");
try {
  const ready = await startCore(nonce);
  console.log(`[dev:web] Core 就绪 pid=${ready.pid} port=${ready.port}`);
  startVite(ready);
  console.log("[dev:web] 打开 http://127.0.0.1:4173 （API 已代理到 Core，写操作可用）");
} catch (error) {
  console.error(`[dev:web] 启动失败：${error.message}`);
  shutdown(1);
}
