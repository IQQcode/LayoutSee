import { createHmac } from "node:crypto";

const VERSION = Object.freeze({ productVersion: "22.6.1", apiVersion: "1.0", snapshotSchemaVersion: "1.0" });

export const SESSION_TOKEN_CONTEXT = "layoutsee-ui-v1";

export function parseReadyLine(line) {
  if (Buffer.byteLength(line, "utf8") > 8192) throw new Error("READY_LINE_TOO_LARGE");
  if (!line.startsWith("READY ")) throw new Error("READY_PREFIX_INVALID");
  const value = JSON.parse(line.slice(6));
  const required = ["port", "pid", "nonce", "productVersion", "apiVersion", "snapshotSchemaVersion"];
  if (required.some((key) => value[key] === undefined)) throw new Error("READY_FIELDS_MISSING");
  if (!Number.isInteger(value.port) || value.port < 1 || value.port > 65535) throw new Error("READY_PORT_INVALID");
  if (!Number.isInteger(value.pid) || value.pid < 1) throw new Error("READY_PID_INVALID");
  if (!/^[a-f0-9]{64}$/.test(value.nonce)) throw new Error("READY_NONCE_INVALID");
  for (const [key, expected] of Object.entries(VERSION)) if (value[key] !== expected) throw new Error("VERSION_INCOMPATIBLE");
  return Object.freeze(value);
}

export function verifyInfo(ready, envelope) {
  if (!envelope?.ok) throw new Error(envelope?.error?.code ?? "CORE_UNAVAILABLE");
  for (const key of ["port", "pid", "nonce", "productVersion", "apiVersion", "snapshotSchemaVersion"]) {
    if (envelope.data[key] !== ready[key]) throw new Error("CORE_IDENTITY_MISMATCH");
  }
  return envelope.data;
}

export function deriveSessionToken(nonce) {
  if (!/^[a-f0-9]{64}$/.test(nonce)) throw new Error("READY_NONCE_INVALID");
  return createHmac("sha256", Buffer.from(nonce, "hex")).update(SESSION_TOKEN_CONTEXT).digest("hex");
}
