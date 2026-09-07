from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from layoutsee_core.diagnostics import diagnose
from layoutsee_core.errors import CoreError
from layoutsee_core.settings import SettingsStore
from layoutsee_core.snapshots import normalize_nodes

XML = """<hierarchy rotation="0">
  <node index="0" text="root" resource-id="" class="android.widget.FrameLayout" package="com.example" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1080,2400]" displayed="true">
    <node index="0" text="超屏按钮" resource-id="" class="android.widget.Button" package="com.example" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1000,300][1200,432]" displayed="true"/>
    <node index="1" text="隐形按钮" resource-id="" class="android.widget.Button" package="com.example" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[3000,300][3100,432]" displayed="false"/>
    <node index="2" text="重叠A" resource-id="" class="android.widget.Button" package="com.example" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[100,800][500,1000]" displayed="true"/>
    <node index="3" text="重叠B" resource-id="" class="android.widget.Button" package="com.example" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[200,820][600,1020]" displayed="true"/>
  </node>
</hierarchy>"""


def make_record():
    nodes, elements, element_to_key = normalize_nodes(XML, {"width": 1080, "height": 2400})
    snapshot = {
        "snapshotId": "snap-diag",
        "windowSizePx": {"width": 1080, "height": 2400},
        "density": 420,
        "nodes": nodes,
    }
    return {"snapshot": snapshot, "elements": elements, "element_to_key": element_to_key, "refs": {}}


class DiagnosticsTest(unittest.TestCase):
    def test_detects_out_of_bounds_and_invisible_interactive(self) -> None:
        result = diagnose(make_record(), "snap-diag")
        types = {finding["type"] for finding in result["findings"]}
        self.assertIn("out_of_bounds", types)
        self.assertIn("invisible_interactive", types)
        self.assertEqual(result["nodesChecked"], 5)
        self.assertIn("overlap", result["rulesChecked"])

    def test_small_touch_target_uses_density(self) -> None:
        xml = '<hierarchy><node index="0" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]"><node index="0" class="android.widget.Button" clickable="true" enabled="true" bounds="[0,0][80,80]"/></node></hierarchy>'
        nodes, elements, element_to_key = normalize_nodes(xml, {"width": 1080, "height": 2400})
        record = {"snapshot": {"snapshotId": "s", "windowSizePx": {"width": 1080, "height": 2400}, "density": 420, "nodes": nodes}, "elements": elements, "element_to_key": element_to_key, "refs": {}}
        result = diagnose(record, "s")
        small = [finding for finding in result["findings"] if finding["type"] == "small_touch_target"]
        self.assertEqual(len(small), 1)
        self.assertEqual(small[0]["confidence"], "high")

    def test_findings_sorted_by_severity(self) -> None:
        result = diagnose(make_record(), "snap-diag")
        order = {"error": 0, "warning": 1, "info": 2}
        ranks = [order[str(finding["severity"])] for finding in result["findings"]]
        self.assertEqual(ranks, sorted(ranks))


class SettingsStoreTest(unittest.TestCase):
    def test_atomic_write_and_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="layoutsee-settings-") as tmp:
            store = SettingsStore(Path(tmp))
            self.assertEqual(store.get()["schemaVersion"], "1.0")
            updated = store.update({"theme": "dark", "pollIntervalMs": 3000})
            self.assertEqual(updated["theme"], "dark")
            reloaded = SettingsStore(Path(tmp))
            self.assertEqual(reloaded.get()["theme"], "dark")
            with self.assertRaises(CoreError):
                store.update({"unknownKey": 1})
            with self.assertRaises(CoreError):
                store.update({"pollIntervalMs": 100})

    def test_schema_version_patch_is_ignored(self) -> None:
        """UI 全量回传设置时，schemaVersion 属系统字段应被静默忽略而非报错。"""
        with tempfile.TemporaryDirectory(prefix="layoutsee-settings-") as tmp:
            store = SettingsStore(Path(tmp))
            updated = store.update({"schemaVersion": "1.0", "theme": "dark"})
            self.assertEqual(updated["schemaVersion"], "1.0")
            self.assertEqual(updated["theme"], "dark")
            self.assertEqual(SettingsStore(Path(tmp)).get()["schemaVersion"], "1.0")


if __name__ == "__main__":
    unittest.main()
