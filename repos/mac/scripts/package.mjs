import { execFile } from "node:child_process";
import { chmod, cp, mkdir, readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { basename, dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const exec = promisify(execFile);
const macRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const workspaceRoot = resolve(macRoot, "../..");
const coreRoot = resolve(workspaceRoot, "repos/core");
const webRoot = resolve(workspaceRoot, "repos/web");
const runtimeRoot = resolve(macRoot, "resources/runtime");
const hostArch = process.arch;
const builderCli = resolve(workspaceRoot, "node_modules/electron-builder/out/cli/cli.js");

if (process.platform !== "darwin") throw new Error("macOS 应用只能在 macOS 上构建");

// ---- CLI：--arch arm64 | x64 | all；缺省 = 构建机架构（兼容既有 `npm run package:mac` 调用）----
const archFlagIndex = process.argv.indexOf("--arch");
const requested = archFlagIndex !== -1 ? process.argv[archFlagIndex + 1] : hostArch;
const archs = requested === "all" ? ["arm64", "x64"] : [requested];
for (const arch of archs) {
  if (arch !== "arm64" && arch !== "x64") throw new Error(`--arch 只接受 arm64 | x64 | all，实际为 ${requested}`);
  // 没有反向转译：x64 主机无法产出 arm64 解释器产物
  if (arch === "arm64" && hostArch !== "arm64") throw new Error(`arm64 制品只能在 arm64 构建机产出，实际主机为 ${hostArch}`);
}

async function run(command, args, options = {}) {
  const result = await exec(command, args, { cwd: workspaceRoot, maxBuffer: 16 * 1024 * 1024, ...options });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
}

async function ready(path) {
  return stat(path).then(() => true).catch(() => false);
}

// 图标唯一事实源是 assets/LayoutSee-1024.png；build/ 下全部为打包时再生的产物。
async function buildIcon() {
  const iconPng = resolve(macRoot, "assets/LayoutSee-1024.png");
  const iconset = resolve(macRoot, "build/LayoutSee.iconset");
  await rm(iconset, { recursive: true, force: true });
  await mkdir(iconset, { recursive: true });
  for (const size of [16, 32, 128, 256, 512]) {
    await run("sips", ["-z", String(size), String(size), iconPng, "--out", resolve(iconset, `icon_${size}x${size}.png`)]);
    await run("sips", ["-z", String(size * 2), String(size * 2), iconPng, "--out", resolve(iconset, `icon_${size}x${size}@2x.png`)]);
  }
  await run("iconutil", ["-c", "icns", iconset, "-o", resolve(macRoot, "build/LayoutSee.icns")]);
}

// ---- core 依赖单一事实源 = repos/core/pyproject.toml（顶层 dependencies + packaging extra）----
async function readCoreDeps() {
  const text = await readFile(resolve(coreRoot, "pyproject.toml"), "utf8");
  const collect = (block) => {
    const deps = [];
    for (const line of block.split("\n")) {
      const hit = line.match(/^\s*"([^"]+)",?\s*$/);
      if (hit) deps.push(hit[1]);
    }
    return deps;
  };
  const deps = [...collect(text.match(/dependencies\s*=\s*\[([\s\S]*?)\]/)?.[1] ?? ""),
    ...collect(text.match(/packaging\s*=\s*\[([\s\S]*?)\]/)?.[1] ?? "")];
  if (!deps.length) throw new Error("pyproject.toml 依赖解析为空");
  return deps;
}

// ---- x86_64 CPython 工具链（python-build-standalone，经 Rosetta 在本机运行）----
// 产物缓存于 repos/mac/build/python-x64（已被根 .gitignore 覆盖）；PyInstaller 必须在目标架构解释器下执行。
const X64_PYTHON = { version: "3.12.14", pbsTag: "20260901" };
const x64Root = resolve(macRoot, "build/python-x64");
const x64VenvPython = resolve(x64Root, "venv/bin/python");
const pbsMirror = process.env.PBS_MIRROR ?? "https://github.com/astral-sh/python-build-standalone/releases/download";

async function ensureX64Toolchain(coreDeps) {
  if (await ready(x64VenvPython)) return;
  // Rosetta 2 是 x86_64 解释器在 arm64 主机运行的前提
  await exec("arch", ["-x86_64", "/usr/bin/true"]).catch(() => {
    throw new Error("x64 构建需要 Rosetta 2，请先执行：softwareupdate --install-rosetta");
  });
  console.log("[toolchain] 下载 x86_64 CPython（python-build-standalone）…");
  await rm(x64Root, { recursive: true, force: true });
  await mkdir(x64Root, { recursive: true });
  const base = `cpython-${X64_PYTHON.version}+${X64_PYTHON.pbsTag}-x86_64-apple-darwin-install_only`;
  const tar = resolve(x64Root, "cpython.tar.gz");
  await exec("curl", ["-fL", "--retry", "3", "-o", tar, `${pbsMirror}/${X64_PYTHON.pbsTag}/${base}.tar.gz`]);
  await exec("tar", ["-xzf", tar, "-C", x64Root]);
  await rm(tar, { force: true });
  const standalonePy = resolve(x64Root, "python/bin/python3.12");
  if (!(await ready(standalonePy))) throw new Error(`x86_64 CPython 解压产物缺失：${standalonePy}`);
  console.log("[toolchain] 创建 x64 venv 并安装依赖…");
  await exec(standalonePy, ["-m", "venv", "--copies", resolve(x64Root, "venv")]);
  await exec(x64VenvPython, ["-m", "pip", "install", "--disable-pip-version-check", "--quiet", ...coreDeps]);
}

// arm64 走项目 uv 环境（与源码测试同源）；x64 走独立 x86_64 venv
async function buildCore(arch, coreDeps) {
  if (arch === "arm64") {
    await run("uv", ["sync", "--project", coreRoot, "--extra", "packaging"]);
  } else {
    await ensureX64Toolchain(coreDeps);
  }
  const prefix = arch === "arm64"
    ? { bin: "uv", args: ["run", "--project", coreRoot, "--extra", "packaging", "pyinstaller"] }
    : { bin: resolve(x64Root, "venv/bin/pyinstaller"), args: [] };
  await exec(prefix.bin, [...prefix.args,
    "--name", "layoutsee-core",
    "--onedir",
    "--clean",
    "--noconfirm",
    "--paths", resolve(coreRoot, "src"),
    "--add-data", `${resolve(coreRoot, "src/layoutsee_core/resources")}:layoutsee_core/resources`,
    // 插件包源码在 repos/plugins，打包时落到 Core 包内 builtin_plugins（bootstrap.builtin_plugins_dir 先找这里）
    "--add-data", `${resolve(workspaceRoot, "repos/plugins")}:layoutsee_core/builtin_plugins`,
    "--distpath", resolve(coreRoot, `dist/${arch}`),
    "--workpath", resolve(coreRoot, `build/pyinstaller-${arch}`),
    "--specpath", resolve(coreRoot, "build/pyinstaller-spec"),
    resolve(coreRoot, "packaging/entrypoint.py"),
  ], { cwd: workspaceRoot, maxBuffer: 16 * 1024 * 1024 });
}

async function listFiles(root) {
  const output = [];
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const path = resolve(root, entry.name);
    if (entry.isDirectory()) output.push(...await listFiles(path));
    else output.push(path);
  }
  return output.sort();
}

async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

async function pythonVersion(arch) {
  const bin = arch === "arm64" ? resolve(coreRoot, ".venv/bin/python") : x64VenvPython;
  const { stdout } = await exec(bin, ["--version"]);
  const m = stdout.match(/Python (\S+)/);
  return m ? m[1] : stdout.trim();
}

// 决策门结论：onefile 在本机每次启动都要 7-8 秒自解压（19.9s 首启动，超过 15s 硬超时）。
// onedir 首启动 8.1s、热启动 0.27s，按 technical-design.md §23.2 切换到 onedir。
async function stageAndManifest(arch) {
  await rm(runtimeRoot, { recursive: true, force: true });
  await mkdir(resolve(runtimeRoot, "core"), { recursive: true });
  await cp(resolve(webRoot, "dist"), resolve(runtimeRoot, "web"), { recursive: true });
  const coreBundle = resolve(coreRoot, `dist/${arch}/layoutsee-core`);
  await cp(resolve(coreBundle, "layoutsee-core"), resolve(runtimeRoot, "core/layoutsee-core"));
  await cp(resolve(coreBundle, "_internal"), resolve(runtimeRoot, "core/_internal"), { recursive: true });
  const coreExecutable = resolve(runtimeRoot, "core/layoutsee-core");
  await chmod(coreExecutable, 0o755);

  const packageJson = JSON.parse(await readFile(resolve(macRoot, "package.json"), "utf8"));
  const webFiles = await listFiles(resolve(runtimeRoot, "web"));
  // scrcpy server（Apache-2.0, https://github.com/Genymobile/scrcpy）；v2.7 jar 随 Core 资源打包
  const scrcpyJar = resolve(runtimeRoot, "core/_internal/layoutsee_core/resources/scrcpy-server-v2.7.jar");
  const scrcpyEntry = (await ready(scrcpyJar))
    ? { version: "2.7", path: "core/_internal/layoutsee_core/resources/scrcpy-server-v2.7.jar", sha256: await sha256(scrcpyJar), license: "Apache-2.0" }
    : null;
  const manifest = {
    schemaVersion: "1.0",
    productVersion: packageJson.version,
    apiVersion: "1.0",
    snapshotSchemaVersion: "1.0",
    targetArch: arch,
    electronVersion: packageJson.devDependencies.electron,
    builderVersion: packageJson.devDependencies["electron-builder"],
    pythonVersion: await pythonVersion(arch),
    core: { path: "core/layoutsee-core", sha256: await sha256(coreExecutable) },
    web: Object.fromEntries(await Promise.all(webFiles.map(async (path) => [relative(runtimeRoot, path), await sha256(path)]))),
    adb: null,
    scrcpy: scrcpyEntry,
    signed: false,
    notarized: false,
  };
  await writeFile(resolve(runtimeRoot, "artifact-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
}

const coreDeps = await readCoreDeps();

console.log("[1/4] 构建正式 Web 资源");
await run("npm", ["--workspace", "@layoutsee/web", "run", "build"]);

console.log("[2/4] 生成应用图标");
await buildIcon();

console.log("[3/4] 构建 Electron 主进程制品");
await run("npm", ["--workspace", "@layoutsee/mac", "run", "build"]);

for (const arch of archs) {
  console.log(`\n===== LayoutSee ${arch} =====`);
  console.log(`[${arch} 1/3] 构建 PyInstaller onedir Core`);
  await buildCore(arch, coreDeps);
  console.log(`[${arch} 2/3] 暂存运行资源与制品清单`);
  await stageAndManifest(arch);
  console.log(`[${arch} 3/3] electron-builder 生成未签名本地手测 DMG`);
  // 网络波动时用 ELECTRON_MIRROR / ELECTRON_BUILDER_BINARIES_MIRROR 前缀重试（见 INDEX.md mac 打包条目）
  await exec(process.execPath, [builderCli, "--config", resolve(macRoot, "electron-builder.yml"), "--mac", "dmg", `--${arch}`], { cwd: macRoot, maxBuffer: 16 * 1024 * 1024 });
  const packageJson = JSON.parse(await readFile(resolve(macRoot, "package.json"), "utf8"));
  // 归档到 release/mac-<arch>/：electron-builder 把解包 .app 放在 release 根的 mac（x64）/
  // mac-arm64（arm64），DMG 落在 release 根 —— 统一收敛成 mac-arm64 / mac-x64 两个交付目录，
  // 安装包与解包 .app 同放一处，避免用户拿错架构。
  const releaseDir = resolve(macRoot, "release");
  const builderAppDir = resolve(releaseDir, arch === "arm64" ? "mac-arm64" : "mac");
  const archDir = resolve(releaseDir, `mac-${arch}`);
  if (resolve(builderAppDir) !== resolve(archDir)) {
    await rm(archDir, { recursive: true, force: true });
    if (await ready(builderAppDir)) await rename(builderAppDir, archDir);
  }
  const dmg = resolve(releaseDir, `LayoutSee-${packageJson.version}-${arch}.dmg`);
  const dmgName = basename(dmg);
  await rename(dmg, resolve(archDir, dmgName));
  const blockmap = resolve(releaseDir, `${dmgName}.blockmap`);
  if (await ready(blockmap)) await rename(blockmap, resolve(archDir, `${dmgName}.blockmap`));
  console.log(`LayoutSee ${packageJson.version} ${arch} 本地候选包已生成 → release/mac-${arch}/${dmgName}`);
}
