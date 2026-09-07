import { access } from "node:fs/promises";

const required = [
  "package-lock.json",
  "repos/contracts/generated/typescript/index.ts",
  "repos/contracts/generated/python/layoutsee_contracts/models.py",
  "repos/core/poetry.lock",
  "repos/core/uv.lock",
  "repos/core/src/layoutsee_core/generated_contracts.py",
  "repos/web/dist/index.html",
  "repos/mac/dist/bootstrap/index.html",
  "repos/mac/dist/shared/handshake.mjs",
  "repos/mac/dist/main/index.mjs",
  "repos/mac/dist/preload/index.cjs",
];

for (const path of required) await access(new URL(`../${path}`, import.meta.url));
console.log(`制品检查通过：${required.length} 个基础制品可用`);
