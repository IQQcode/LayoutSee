const { execFileSync } = require("node:child_process");
const { join } = require("node:path");
const { readdirSync, rmSync } = require("node:fs");

// 保留的系统本地化目录白名单（en + 简繁中文）。Electron 44 分发 44 种语言 ×
// （主目录 + 3 个语法性别变体），Framework 内 locale.pak 合计约 50MB（未压缩）；
// 应用界面文字全部由代码自绘，不依赖这些资源，删掉的目录仅在系统级弹窗
// （保存面板、权限提示等）以对应系统语言显示时回退英文。
const KEEP_LPROJ = new Set(["en.lproj", "zh_CN.lproj", "zh_TW.lproj"]);

function removableLproj(dir) {
  try {
    return readdirSync(dir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && entry.name.endsWith(".lproj") && !KEEP_LPROJ.has(entry.name))
      .map((entry) => entry.name)
      .sort();
  } catch {
    return []; // 目录不存在（结构变化）时静默跳过，不阻断打包
  }
}

module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== "darwin") return;
  const appContents = join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`, "Contents");
  const plist = join(appContents, "Info.plist");
  const plistBuddy = "/usr/libexec/PlistBuddy";
  execFileSync(plistBuddy, ["-c", "Set :NSAppTransportSecurity:NSAllowsArbitraryLoads false", plist]);
  for (const key of [
    "NSAudioCaptureUsageDescription",
    "NSBluetoothAlwaysUsageDescription",
    "NSBluetoothPeripheralUsageDescription",
    "NSCameraUsageDescription",
    "NSMicrophoneUsageDescription",
  ]) {
    try {
      execFileSync(plistBuddy, ["-c", `Delete :${key}`, plist], { stdio: "ignore" });
    } catch {
      // 对应权限键不存在时无需处理。
    }
  }

  // 本地化裁剪：app 顶层 Resources（Electron 44 里全为空目录）+
  // Electron Framework 内 Resources（locale.pak 大头所在）。
  const resourceDirs = [
    join(appContents, "Resources"),
    join(appContents, "Frameworks", "Electron Framework.framework", "Versions", "A", "Resources"),
  ];
  for (const dir of resourceDirs) {
    const removed = removableLproj(dir);
    for (const name of removed) rmSync(join(dir, name), { recursive: true, force: true });
    if (removed.length) console.log(`[after-pack] 已裁剪本地化目录 ${removed.length} 个 → ${join(dir, "…")}`);
  }
};
