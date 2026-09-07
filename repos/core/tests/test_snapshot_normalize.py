from __future__ import annotations

import unittest

from layoutsee_core.snapshots import normalize_nodes, png_size

SAMPLE_XML = """<hierarchy rotation="0">
  <node index="0" text="root" resource-id="com.example:id/root" class="android.widget.FrameLayout" package="com.example" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1080,2400]" displayed="true">
    <node index="0" text="登录" resource-id="com.example:id/login" class="android.widget.Button" package="com.example" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[96,300][984,432]" displayed="true"/>
    <node index="1" text="列表" resource-id="" class="androidx.recyclerview.widget.RecyclerView" package="com.example" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="true" long-clickable="false" password="false" selected="false" bounds="[0,500][1080,2400]" displayed="true">
      <node index="0" text="第一条" resource-id="" class="android.widget.TextView" package="com.example" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[40,540][1040,640]" displayed="true"/>
    </node>
  </node>
</hierarchy>"""


class NormalizeTest(unittest.TestCase):
    def test_node_tree_uses_stable_path_keys_and_normalized_bounds(self) -> None:
        nodes, elements, element_to_key = normalize_nodes(SAMPLE_XML, {"width": 1080, "height": 2400})
        self.assertEqual(len(nodes), 4)
        self.assertEqual([node["nodeKey"] for node in nodes], ["0", "0.0", "0.1", "0.1.0"])
        button = nodes[1]
        self.assertTrue(button["clickable"])
        self.assertEqual(button["text"], "登录")
        self.assertEqual(button["boundsPx"], {"left": 96, "top": 300, "right": 984, "bottom": 432})
        self.assertAlmostEqual(button["boundsNormalized"]["left"], 96 / 1080, places=6)
        self.assertAlmostEqual(button["boundsNormalized"]["bottom"], 432 / 2400, places=6)
        self.assertEqual(button["parentKey"], "0")
        self.assertEqual(len(elements), 4)
        self.assertIn(id(elements[1]), element_to_key)

    def test_rejects_dtd_and_malformed_xml(self) -> None:
        nodes, _, _ = normalize_nodes("<!DOCTYPE hierarchy [<!ENTITY x 'y'>]><hierarchy/>", {"width": 1080, "height": 2400})
        self.assertEqual(nodes, [])
        nodes, _, _ = normalize_nodes("<hierarchy><node", {"width": 1080, "height": 2400})
        self.assertEqual(nodes, [])

    def test_nodes_without_bounds_inherit_parent_bounds_and_are_invisible(self) -> None:
        xml = '<hierarchy><node index="0" class="android.view.View" bounds="[0,0][100,100]"><node index="0" class="android.view.View"/></node></hierarchy>'
        nodes, _, _ = normalize_nodes(xml, {"width": 100, "height": 100})
        self.assertEqual(len(nodes), 2)
        self.assertFalse(nodes[1]["visible"])
        self.assertEqual(nodes[1]["boundsPx"], {"left": 0, "top": 0, "right": 100, "bottom": 100})

    def test_png_size_reads_ihdr(self) -> None:
        png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (16).to_bytes(4, "big") + (32).to_bytes(4, "big") + b"\x00" * 8)
        self.assertEqual(png_size(png), (16, 32))
        self.assertIsNone(png_size(b"not-a-png"))


if __name__ == "__main__":
    unittest.main()
