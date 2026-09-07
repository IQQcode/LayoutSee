import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
await rm(resolve(root, "dist"), { recursive: true, force: true });
await mkdir(resolve(root, "dist/bootstrap"), { recursive: true });
await mkdir(resolve(root, "dist/main"), { recursive: true });
await mkdir(resolve(root, "dist/preload"), { recursive: true });
await mkdir(resolve(root, "dist/shared"), { recursive: true });
await cp(resolve(root, "src/bootstrap/index.html"), resolve(root, "dist/bootstrap/index.html"));
await cp(resolve(root, "src/shared/handshake.mjs"), resolve(root, "dist/shared/handshake.mjs"));
await cp(resolve(root, "src/main"), resolve(root, "dist/main"), { recursive: true });
await cp(resolve(root, "src/preload"), resolve(root, "dist/preload"), { recursive: true });
console.log("macOS 壳主进程与启动制品已生成");
