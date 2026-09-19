import { parseReadyLine, verifyInfo } from "../src/shared/handshake.mjs";

const nonce = "0".repeat(64);
const ready = parseReadyLine(`READY ${JSON.stringify({ port: 11663, pid: 1, nonce, productVersion: "22.6.1", apiVersion: "1.0", snapshotSchemaVersion: "1.0" })}`);
verifyInfo(ready, { ok: true, data: ready, requestId: "req-lint-0001" });
console.log("macOS 壳握手静态检查通过");

