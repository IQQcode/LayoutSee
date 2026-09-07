from __future__ import annotations

import unittest

from layoutsee_core.snapshots import normalize_nodes
from layoutsee_core.summary import summarize
from layoutsee_core.selectors import generate_selectors

XML = """<hierarchy rotation="0">
  <node index="0" text="root" resource-id="com.example:id/root" class="android.widget.FrameLayout" package="com.example" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1080,2400]" displayed="true">
    <node index="0" text="登录" resource-id="com.example:id/login" class="android.widget.Button" package="com.example" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[96,300][984,432]" displayed="true"/>
    <node index="1" text="" resource-id="com.example:id/name" class="android.widget.EditText" package="com.example" content-desc="请输入姓名" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[96,600][984,732]" displayed="true"/>
  </node>
</hierarchy>"""


def make_record():
    nodes, elements, element_to_key = normalize_nodes(XML, {"width": 1080, "height": 2400})
    refs = {node["nodeKey"]: f"r{node['nodeKey'].replace('.', 'x')}" for node in nodes}
    return {"snapshot": {"snapshotId": "snap-test", "nodes": nodes}, "elements": elements, "element_to_key": element_to_key, "refs": refs, "ref_token": "x"}


class SummaryTest(unittest.TestCase):
    def test_summary_is_deterministic(self) -> None:
        record = make_record()
        first = summarize(record, "snap-test")
        second = summarize(record, "snap-test")
        self.assertEqual(first, second)

    def test_summary_includes_all_interactive_nodes(self) -> None:
        record = make_record()
        result = summarize(record, "snap-test")
        self.assertEqual(result["coverage"]["totalInteractive"], 2)
        self.assertEqual(result["coverage"]["includedInteractive"], 2)
        self.assertEqual(result["coverage"]["omittedInteractive"], 0)
        self.assertIn("登录", result["text"])
        self.assertIn("输入框", result["text"])
        self.assertGreater(result["estimatedTokens"], 0)

    def test_selector_candidates_report_real_match_counts(self) -> None:
        record = make_record()
        result = generate_selectors(record, "0.0")
        self.assertGreater(len(result["selectors"]), 0)
        for selector in result["selectors"]:
            self.assertEqual(selector["matchCount"], 1)
            self.assertTrue(selector["stable"])
        # 唯一 id 候选应命中同一节点
        self.assertIn("com.example:id/login", result["selectors"][0]["expression"])


if __name__ == "__main__":
    unittest.main()
