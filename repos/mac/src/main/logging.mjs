import { appendFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

export function redactSecrets(value, secrets = []) {
  let output = String(value ?? "");
  for (const secret of secrets) {
    if (typeof secret === "string" && secret.length >= 16) output = output.split(secret).join("[已脱敏]");
  }
  return output
    .replace(/("nonce"\s*:\s*")[^"]+("?)/gi, "$1[已脱敏]$2")
    .replace(/(authorization\s*:\s*bearer\s+)[^\s]+/gi, "$1[已脱敏]")
    .replace(/(password|token|credential)(\s*[=:]\s*)[^\s,;]+/gi, "$1$2[已脱敏]");
}

export class DailyFileLogger {
  constructor(directory) {
    this.directory = directory;
  }

  pathFor(channel, date = new Date()) {
    const day = date.toISOString().slice(0, 10);
    return join(this.directory, `${day}-${channel}.log`);
  }

  async ensureDirectory() {
    await mkdir(this.directory, { recursive: true });
  }

  write(channel, message, secrets = []) {
    const safeChannel = channel === "core" ? "core" : "shell";
    const line = `${new Date().toISOString()} ${redactSecrets(message, secrets).trimEnd()}\n`;
    void this.ensureDirectory()
      .then(() => appendFile(this.pathFor(safeChannel), line, { encoding: "utf8", mode: 0o600 }))
      .catch(() => {});
  }
}
