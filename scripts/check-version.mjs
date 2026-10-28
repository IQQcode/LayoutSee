// 版本号一致性门禁：唯一事实源 = 根 package.json 的 version。
// 覆盖 INDEX.md 原人工清单的全部位置；插件 engines 兼容区间只校验根版本落在区间内。
// 运行：npm run version:check（已接入 lint 链）。
import { readFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const problems = [];
const expected = JSON.parse(await readFile(resolve(root, "package.json"), "utf8")).version;
if (!/^\d+\.\d+\.\d+$/.test(expected)) problems.push(`根 package.json 的 version 非法：${expected}`);

async function readJson(relative) {
  return JSON.parse(await readFile(resolve(root, relative), "utf8"));
}
async function readText(relative) {
  return readFile(resolve(root, relative), "utf8");
}
function checkEqual(label, actual) {
  if (actual !== expected) problems.push(`${label}：${actual} ≠ ${expected}`);
}
function semverCompare(a, b) {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < 3; i += 1) {
    if (pa[i] !== pb[i]) return pa[i] - pb[i];
  }
  return 0;
}

// workspace 各包版本
for (const relative of ["repos/contracts/package.json", "repos/web/package.json", "repos/mac/package.json"]) {
  const json = await readJson(relative);
  checkEqual(relative, json.version);
}

// lockfile：根条目与 @layoutsee/contracts 依赖 pin
const lock = await readJson("package-lock.json");
checkEqual("package-lock.json 根 .version", lock.version);
checkEqual("package-lock.json packages[''].version", lock.packages?.[""]?.version);
const contractsPin = lock.packages?.["repos/web"]?.dependencies?.["@layoutsee/contracts"]
  ?? lock.packages?.["repos/mac"]?.dependencies?.["@layoutsee/contracts"];
checkEqual("package-lock.json @layoutsee/contracts pin", contractsPin);

// Python：pyproject dynamic（不得再有静态 version）、__init__ 单源、bootstrap 引用而非字面量
const pyproject = await readText("repos/core/pyproject.toml");
if (!/^dynamic = \["version"\]$/m.test(pyproject)) problems.push("repos/core/pyproject.toml：缺少 dynamic = [\"version\"]");
if (/^version\s*=\s*"/m.test(pyproject)) problems.push("repos/core/pyproject.toml：仍保留静态 version 字面量");
const initPy = await readText("repos/core/src/layoutsee_core/__init__.py");
if (!new RegExp(`__version__ = "${expected}"`).test(initPy)) {
  problems.push(`repos/core/src/layoutsee_core/__init__.py：__version__ ≠ ${expected}`);
}
const bootstrap = await readText("repos/core/src/layoutsee_core/bootstrap.py");
if (/PRODUCT_VERSION\s*=\s*"/.test(bootstrap)) {
  problems.push("repos/core/src/layoutsee_core/bootstrap.py：PRODUCT_VERSION 不得写字面量，应 from . import __version__");
}
if (!/from \. import __version__ as PRODUCT_VERSION/.test(bootstrap)) {
  problems.push("repos/core/src/layoutsee_core/bootstrap.py：缺少 from . import __version__ as PRODUCT_VERSION");
}

// 契约：info.json 的 const 与两处生成物
const info = await readJson("repos/contracts/schemas/common/info.json");
checkEqual("repos/contracts/schemas/common/info.json productVersion.const", info.properties?.productVersion?.const);
for (const relative of [
  "repos/core/src/layoutsee_core/generated_contracts.py",
  "repos/contracts/generated/typescript/index.ts",
]) {
  const text = await readText(relative);
  if (!text.includes(`"${expected}"`)) problems.push(`${relative}：生成物缺少 "${expected}"（需跑 npm run contracts:generate）`);
}

// mac 壳握手金样
const handshake = await readText("repos/mac/src/shared/handshake.mjs");
if (!new RegExp(`productVersion: "${expected}"`).test(handshake)) {
  problems.push(`repos/mac/src/shared/handshake.mjs：productVersion ≠ ${expected}`);
}

// 内置插件 engines：根版本必须落在兼容区间内（区间本身允许滞后下界）
const { readdir } = await import("node:fs/promises");
const pluginDirs = await readdir(resolve(root, "repos/plugins"), { withFileTypes: true });
for (const entry of pluginDirs.filter((item) => item.isDirectory())) {
  try {
    const manifest = await readJson(`repos/plugins/${entry.name}/manifest.json`);
    const range = manifest?.engines?.layoutsee;
    if (typeof range !== "string") continue;
    const lower = range.match(/>=\s*(\d+\.\d+\.\d+)/)?.[1];
    const upper = range.match(/<\s*(\d+\.\d+\.\d+)/)?.[1];
    if (lower && semverCompare(expected, lower) < 0) {
      problems.push(`repos/plugins/${entry.name}：engines 下界 ${lower} 高于根版本 ${expected}`);
    }
    if (upper && semverCompare(expected, upper) >= 0) {
      problems.push(`repos/plugins/${entry.name}：engines 上界 ${upper} 低于等于根版本 ${expected}`);
    }
  } catch {
    // 无 manifest 的目录跳过
  }
}

if (problems.length) {
  console.error(`版本号不一致（期望 ${expected}）：`);
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}
console.log(`版本号一致：${expected}（version:check 全部通过）`);
