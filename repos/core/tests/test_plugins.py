from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from layoutsee_core.errors import CoreError
from layoutsee_core.plugins import PluginRegistry


def write_plugin(root: Path, plugin_id: str, **overrides: object) -> Path:
    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "schemaVersion": "2.0",
        "id": plugin_id,
        "name": f"插件 {plugin_id}",
        "version": "1.0.0",
        "activation": "onOpen",
        "contributions": {"workbenchTabs": [{"id": "main", "title": "主页", "entry": "index.html"}]},
    }
    manifest.update(overrides)
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (directory / "index.html").write_text("<!doctype html><title>p</title>", encoding="utf-8")
    return directory


class PluginRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-plugins-")
        root = Path(self.temp.name)
        self.local = root / "local"
        self.builtin = root / "builtin"
        self.local.mkdir()
        self.builtin.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def registry(self) -> PluginRegistry:
        return PluginRegistry(self.local, builtin_dir=self.builtin, product_version="0.2.0")

    def entry_of(self, payload: dict[str, object], plugin_id: str) -> dict[str, object]:
        for item in payload["items"]:
            if item.get("id") == plugin_id:
                return item
        raise AssertionError(f"索引里没有 {plugin_id}")

    def test_construction_does_not_touch_disk(self) -> None:
        """冷启动预算的硬性约束：装配阶段既不 iterdir 也不 stat。"""
        with mock.patch.object(Path, "iterdir", side_effect=AssertionError("启动路径不允许扫盘")), mock.patch.object(
            Path, "stat", side_effect=AssertionError("启动路径不允许 stat")
        ):
            registry = self.registry()
        self.assertEqual(registry.parse_count, 0)

    def test_cache_hit_skips_reparsing(self) -> None:
        write_plugin(self.local, "alpha")
        write_plugin(self.local, "beta")
        registry = self.registry()
        first = registry.index()
        self.assertFalse(first["cacheHit"])
        self.assertEqual(registry.parse_count, 2)
        second = registry.index()
        self.assertTrue(second["cacheHit"])
        self.assertEqual(registry.parse_count, 2)
        self.assertFalse(registry.index(refresh=True)["cacheHit"])
        self.assertEqual(registry.parse_count, 4)

    def test_disk_cache_serves_fresh_process(self) -> None:
        write_plugin(self.local, "alpha")
        self.registry().index()
        reborn = self.registry()
        payload = reborn.index()
        self.assertTrue(payload["cacheHit"])
        self.assertEqual(reborn.parse_count, 0)
        self.assertEqual(self.entry_of(payload, "alpha")["status"], "ready")

    def test_signature_change_invalidates_cache(self) -> None:
        write_plugin(self.local, "alpha")
        registry = self.registry()
        registry.index()
        write_plugin(self.local, "alpha", name="改名后的插件")
        payload = registry.index()
        self.assertFalse(payload["cacheHit"])
        self.assertEqual(self.entry_of(payload, "alpha")["name"], "改名后的插件")

    def test_local_overrides_builtin(self) -> None:
        write_plugin(self.builtin, "shared", version="1.0.0")
        write_plugin(self.local, "shared", version="2.0.0")
        entry = self.entry_of(self.registry().index(), "shared")
        self.assertEqual(entry["origin"], "local")
        self.assertEqual(entry["version"], "2.0.0")
        self.assertEqual(entry["overrides"], "builtin")

    def test_engines_mismatch_marks_incompatible(self) -> None:
        write_plugin(self.local, "future", engines={"layoutsee": ">=9.0.0"})
        entry = self.entry_of(self.registry().index(), "future")
        self.assertEqual(entry["status"], "incompatible")
        self.assertEqual(entry["error"]["code"], "PLUGIN_INCOMPATIBLE")

    def test_broken_manifest_is_invalid_not_fatal(self) -> None:
        directory = self.local / "broken"
        directory.mkdir()
        (directory / "manifest.json").write_text("{not json", encoding="utf-8")
        write_plugin(self.local, "alpha")
        payload = self.registry().index()
        self.assertEqual(self.entry_of(payload, "broken")["status"], "invalid")
        self.assertEqual(self.entry_of(payload, "alpha")["status"], "ready")

    def test_legacy_manifest_upgraded(self) -> None:
        directory = self.local / "legacy"
        directory.mkdir()
        (directory / "index.html").write_text("<!doctype html>", encoding="utf-8")
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "schemaVersion": "1.0",
                    "id": "legacy",
                    "name": "老插件",
                    "version": "0.1.0",
                    "entry": "index.html",
                    "platforms": ["android", "macos"],
                    "permissions": ["device.read", "network.none"],
                }
            ),
            encoding="utf-8",
        )
        entry = self.entry_of(self.registry().index(), "legacy")
        self.assertEqual(entry["status"], "ready")
        self.assertTrue(entry["legacy"])
        self.assertEqual(entry["devicePlatforms"], ["android"])
        self.assertEqual(entry["permissions"], ["device.read"])
        self.assertEqual(entry["contributions"]["workbenchTabs"][0]["entry"], "index.html")

    def test_asset_escape_symlink_and_suffix_rejected(self) -> None:
        directory = write_plugin(self.local, "alpha")
        (Path(self.temp.name) / "outside.html").write_text("<!doctype html>", encoding="utf-8")
        (directory / "notes.txt").write_text("plain", encoding="utf-8")
        (directory / "linked.html").symlink_to(Path(self.temp.name) / "outside.html")
        registry = self.registry()
        self.assertTrue(registry.resolve_asset("alpha", "index.html").is_file())
        for bad in ("../outside.html", "/etc/hosts", "..\\outside.html", ".hidden/index.html"):
            with self.assertRaises(CoreError) as caught:
                registry.resolve_asset("alpha", bad)
            self.assertEqual(caught.exception.code, "PERMISSION_REQUIRED")
        with self.assertRaises(CoreError) as symlink_error:
            registry.resolve_asset("alpha", "linked.html")
        self.assertEqual(symlink_error.exception.code, "PERMISSION_REQUIRED")
        with self.assertRaises(CoreError) as suffix_error:
            registry.resolve_asset("alpha", "notes.txt")
        self.assertEqual(suffix_error.exception.code, "PLUGIN_NOT_FOUND")
        with self.assertRaises(CoreError) as missing:
            registry.resolve_asset("ghost", "index.html")
        self.assertEqual(missing.exception.code, "PLUGIN_NOT_FOUND")

    def test_fifty_plugins_stay_within_budget(self) -> None:
        for index in range(50):
            write_plugin(self.local, f"p{index:02d}")
        registry = self.registry()
        cold_started = time.monotonic()
        payload = registry.index()
        cold_ms = (time.monotonic() - cold_started) * 1000
        self.assertEqual(len(payload["items"]), 50)
        warm_started = time.monotonic()
        self.assertTrue(registry.index()["cacheHit"])
        warm_ms = (time.monotonic() - warm_started) * 1000
        self.assertLess(cold_ms, 150, f"50 个插件冷解析耗时 {cold_ms:.1f}ms，超出 150ms 预算")
        self.assertLess(warm_ms, 15, f"签名命中耗时 {warm_ms:.1f}ms，超出 15ms 预算")


if __name__ == "__main__":
    unittest.main()
