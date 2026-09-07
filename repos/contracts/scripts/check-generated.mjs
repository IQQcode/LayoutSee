import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { listFiles } from "./lib.mjs";

const exec = promisify(execFile);
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const committed = resolve(packageRoot, "generated");
const temporary = await mkdtemp(resolve(tmpdir(), "layoutsee-contracts-"));

try {
  await exec(process.execPath, [resolve(packageRoot, "scripts/generate.mjs"), "--output", temporary]);
  const expectedFiles = (await listFiles(temporary)).map((path) => relative(temporary, path));
  const actualFiles = (await listFiles(committed)).map((path) => relative(committed, path));
  if (JSON.stringify(expectedFiles) !== JSON.stringify(actualFiles)) throw new Error("生成文件清单发生漂移，请运行 npm run contracts:generate");
  for (const file of expectedFiles) {
    const expected = await readFile(resolve(temporary, file));
    const actual = await readFile(resolve(committed, file));
    if (!expected.equals(actual)) throw new Error(`生成文件发生漂移：${file}`);
  }
  const generatedCore = await readFile(resolve(packageRoot, "../core/src/layoutsee_core/generated_contracts.py"));
  const expectedCore = await readFile(resolve(temporary, "python/layoutsee_contracts/models.py"));
  if (!generatedCore.equals(expectedCore)) throw new Error("Core 生成模型发生漂移，请运行 npm run contracts:generate");
  console.log(`契约生成物一致：${expectedFiles.length} 个文件`);
} finally {
  await rm(temporary, { recursive: true, force: true });
}
