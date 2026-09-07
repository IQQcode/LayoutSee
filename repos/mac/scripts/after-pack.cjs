const { execFileSync } = require("node:child_process");
const { join } = require("node:path");

module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== "darwin") return;
  const plist = join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`, "Contents", "Info.plist");
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
}
