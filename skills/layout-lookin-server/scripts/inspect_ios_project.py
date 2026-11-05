#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iOS 工程摸底脚本（只读）。

为 LookinServer 集成收集事实：Podfile / Podfile.lock / .xcodeproj / Package.swift 是否存在、
各工程的 build configuration 名与 target 名、Swift / OC 文件占比、是否已集成 LookinServer。
仅依赖 Python 标准库；只读本地文件，无网络、无子进程。

用法：
    python3 inspect_ios_project.py <工程目录>    # 输出 JSON
"""
import json
import os
import re
import sys
from pathlib import Path

LOOKIN_REPO_MARKER = "QMUI/LookinServer"
LOOKIN_RECOMMENDED_VERSION = "1.2.8"

# 摸底时跳过的目录（依赖与产物目录不参与语言统计，也不在其下找 Podfile）
SKIP_DIR_NAMES = {".git", "Pods", "node_modules", "DerivedData", "build", "Carthage", "vendor", ".build"}
MAX_FILES = 20000

POD_LOOKIN_RE = re.compile(r"^\s*pod\s+['\"]LookinServer['\"](.*)$", re.MULTILINE)
POD_TARGET_RE = re.compile(r"^\s*target\s+['\"]([^'\"]+)['\"]\s+do\b", re.MULTILINE)
LOCK_LOOKIN_RE = re.compile(r"^\s*-?\s*LookinServer\s+\(([\d.]+)\)", re.MULTILINE)
PBX_NAME_RE = re.compile(r"\bname\s*=\s*\"?([^;\"\n]+)\"?\s*;")
SPM_MIN_VERSION_RE = re.compile(r"minimumVersion\s*=\s*([\d.]+)")


def scan_tree(root):
    podfile = None
    podfile_lock = None
    package_swift = None
    xcodeprojects = []
    swift_files = 0
    objc_files = 0
    visited = 0
    truncated = False
    for current, dirs, names in os.walk(root):
        keep = []
        for name in dirs:
            if name.endswith(".xcodeproj"):
                xcodeprojects.append(Path(current) / name)
            elif name not in SKIP_DIR_NAMES and not name.startswith("."):
                keep.append(name)
        dirs[:] = keep
        for name in names:
            visited += 1
            if visited > MAX_FILES:
                truncated = True
                break
            path = Path(current) / name
            rel = path.relative_to(root)
            if name == "Podfile" and podfile is None:
                podfile = rel
            elif name == "Podfile.lock" and podfile_lock is None:
                podfile_lock = rel
            elif name == "Package.swift" and package_swift is None:
                package_swift = rel
            elif name.endswith(".swift"):
                swift_files += 1
            elif name.endswith((".m", ".mm")):
                objc_files += 1
        if truncated:
            break
    return {
        "podfile": podfile,
        "podfile_lock": podfile_lock,
        "package_swift": package_swift,
        "xcodeprojects": sorted(xcodeprojects),
        "swift_files": swift_files,
        "objc_files": objc_files,
        "truncated": truncated,
    }


def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ""


def parse_podfile(root, rel):
    if rel is None:
        return {"present": False, "hasLookinServer": False, "lookinPodLine": None, "targets": []}
    text = read_text(root / rel)
    matches = POD_LOOKIN_RE.findall(text)
    return {
        "present": True,
        "hasLookinServer": bool(matches),
        "lookinPodLine": matches[0].strip() if matches else None,
        "targets": POD_TARGET_RE.findall(text),
    }


def parse_pbxproj(path):
    text = read_text(path)
    if not text:
        return {"error": f"无法读取 {path.name}"}
    configurations = []
    for chunk in text.split("isa = XCBuildConfiguration")[1:]:
        match = PBX_NAME_RE.search(chunk[:600])
        if match:
            name = match.group(1).strip()
            if name not in configurations:
                configurations.append(name)
    targets = []
    for chunk in text.split("isa = PBXNativeTarget")[1:]:
        match = PBX_NAME_RE.search(chunk[:600])
        if match:
            targets.append(match.group(1).strip())
    spm = "XCRemoteSwiftPackageReference" in text and LOOKIN_REPO_MARKER in text
    spm_minimum = None
    if spm:
        for chunk in text.split("XCRemoteSwiftPackageReference")[1:]:
            if LOOKIN_REPO_MARKER in chunk:
                match = SPM_MIN_VERSION_RE.search(chunk[:800])
                if match:
                    spm_minimum = match.group(1)
                break
    return {
        "targets": targets,
        "configurations": configurations,
        "debugLike": [name for name in configurations if "debug" in name.lower()],
        "spm": spm,
        "spmMinimumVersion": spm_minimum,
        "lookinMentions": "LookinServer" in text,
    }


def build_verdict(podfile, lock_version, projects, package_swift):
    if lock_version or (podfile and podfile.get("hasLookinServer")):
        return "cocoapods-integrated"
    if any(project.get("spm") for project in projects):
        return "spm-integrated"
    if any(project.get("lookinMentions") for project in projects):
        return "possibly-integrated"
    if podfile and podfile.get("present"):
        return "recommend-cocoapods"
    if projects:
        return "recommend-spm"
    if package_swift:
        return "swiftpm-package"
    return "unknown"


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip(), file=sys.stderr)
        raise SystemExit(0 if "-h" in sys.argv or "--help" in sys.argv else 2)
    root = Path(sys.argv[1]).expanduser().resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"目录不存在或不是目录: {root}"}, ensure_ascii=False))
        raise SystemExit(2)

    tree = scan_tree(root)
    podfile = parse_podfile(root, tree["podfile"])
    lock_version = None
    if tree["podfile_lock"] is not None:
        match = LOCK_LOOKIN_RE.search(read_text(root / tree["podfile_lock"]))
        lock_version = match.group(1) if match else None
    projects = []
    for project_dir in tree["xcodeprojects"]:
        record = {"path": str(project_dir.relative_to(root))}
        record.update(parse_pbxproj(project_dir / "project.pbxproj"))
        projects.append(record)
    if tree["swift_files"] >= tree["objc_files"] and tree["swift_files"] > 0:
        primary = "swift"
    elif tree["objc_files"] > 0:
        primary = "objc"
    else:
        primary = "unknown"
    verdict = build_verdict(podfile, lock_version, projects, tree["package_swift"])

    notes = []
    if lock_version and lock_version != LOOKIN_RECOMMENDED_VERSION:
        notes.append(f"已集成版本 {lock_version}，LayoutSee 支持协议 7（LookinServer 1.1.8~1.2.8），建议统一到 {LOOKIN_RECOMMENDED_VERSION}")
    if podfile.get("hasLookinServer") and not lock_version:
        notes.append("Podfile 已声明 LookinServer 但 Podfile.lock 无记录：尚未 pod install")
    if any(project.get("spm") for project in projects):
        versions = [project.get("spmMinimumVersion") for project in projects if project.get("spm")]
        notes.append("SPM 依赖不落 lock 文件；建议 rule 为 upToNextMajorVersion + minimumVersion 1.2.8"
                     + (f"（当前 minimumVersion={versions[0]}）" if versions and versions[0] else ""))
    if tree["truncated"]:
        notes.append(f"扫描文件数超过上限 {MAX_FILES}，结果可能不完整")
    if verdict == "unknown":
        notes.append("未发现 Podfile / .xcodeproj / Package.swift，请确认传入的是 iOS App 工程根目录")

    print(json.dumps({
        "root": str(root),
        "truncated": tree["truncated"],
        "podfile": str(tree["podfile"]) if tree["podfile"] else None,
        "podfileHasLookinServer": podfile.get("hasLookinServer", False),
        "podfileLookinPodLine": podfile.get("lookinPodLine"),
        "podfileTargets": podfile.get("targets", []),
        "podfileLock": str(tree["podfile_lock"]) if tree["podfile_lock"] else None,
        "podfileLockLookinServerVersion": lock_version,
        "packageSwift": str(tree["package_swift"]) if tree["package_swift"] else None,
        "xcodeprojects": projects,
        "language": {"swift": tree["swift_files"], "objc": tree["objc_files"], "primary": primary},
        "verdict": verdict,
        "recommendedVersion": LOOKIN_RECOMMENDED_VERSION,
        "notes": notes,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
