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
    return {"snapshot": {"snapshotId": "snap-test", "nodes": nodes}, "elements": elements, "element_to_key": element_to_key, "refs": refs, "ref_token": "x", "xml": XML}


def make_dense_record(count: int = 120):
    """构造可交互元素累计超预算的密集页，用于验证可交互必保留底线。"""
    buttons = "".join(
        f'<node index="{i}" text="按钮项目{i}号内容" resource-id="com.example:id/btn{i}" '
        f'class="android.widget.Button" package="com.example" content-desc="" checkable="false" '
        f'checked="false" clickable="true" enabled="true" focusable="true" focused="false" '
        f'scrollable="false" long-clickable="false" password="false" selected="false" '
        f'bounds="[0,{i * 20}][1080,{i * 20 + 18}]" displayed="true"/>'
        for i in range(count)
    )
    xml = (
        '<hierarchy rotation="0"><node index="0" class="android.widget.FrameLayout" '
        f'bounds="[0,0][1080,2400]">{buttons}</node></hierarchy>'
    )
    nodes, elements, element_to_key = normalize_nodes(xml, {"width": 1080, "height": 2400})
    refs = {node["nodeKey"]: f"r{node['nodeKey'].replace('.', 'x')}" for node in nodes}
    return {"snapshot": {"snapshotId": "snap-dense", "nodes": nodes}, "elements": elements, "element_to_key": element_to_key, "refs": refs, "ref_token": "x", "xml": xml}


class SummaryTest(unittest.TestCase):
    def test_summary_is_deterministic(self) -> None:
        record = make_record()
        self.assertEqual(summarize(record, "snap-test"), summarize(record, "snap-test"))

    def test_summary_includes_all_interactive_nodes(self) -> None:
        result = summarize(make_record(), "snap-test")
        self.assertEqual(result["coverage"]["totalInteractive"], 2)
        self.assertEqual(result["coverage"]["includedInteractive"], 2)
        self.assertEqual(result["coverage"]["omittedInteractive"], 0)
        self.assertIn("登录", result["text"])
        self.assertIn("输入框", result["text"])
        self.assertGreater(result["estimatedTokens"], 0)

    def test_max_tokens_defaults_and_falls_back(self) -> None:
        self.assertEqual(summarize(make_record(), "snap-test")["maxTokens"], 1200)
        self.assertEqual(summarize(make_record(), "snap-test", max_tokens=0)["maxTokens"], 1200)
        self.assertEqual(summarize(make_record(), "snap-test", max_tokens=None)["maxTokens"], 1200)
        self.assertEqual(summarize(make_record(), "snap-test", max_tokens=500)["maxTokens"], 500)

    def test_dense_page_never_omits_interactive(self) -> None:
        result = summarize(make_dense_record(), "snap-dense", max_tokens=1200)
        coverage = result["coverage"]
        self.assertGreater(coverage["totalInteractive"], 60)
        self.assertEqual(coverage["omittedInteractive"], 0)
        self.assertEqual(coverage["includedInteractive"], coverage["totalInteractive"])
        self.assertTrue(result["interactiveOverBudget"])

    def test_compression_ratio_reported(self) -> None:
        result = summarize(make_dense_record(), "snap-dense")
        ratio = result["compressionRatio"]
        self.assertEqual(ratio["summaryChars"], len(result["text"]))
        self.assertGreater(ratio["rawChars"], 0)
        self.assertIsNotNone(ratio["ratio"])

    def test_summary_degrades_without_raising(self) -> None:
        broken = make_record()
        broken["refs"] = {}
        result = summarize(broken, "snap-test")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["coverage"]["omittedInteractive"], 0)
        self.assertTrue(result["text"])

    def test_selector_candidates_report_real_match_counts(self) -> None:
        result = generate_selectors(make_record(), "0.0")
        self.assertGreater(len(result["selectors"]), 0)
        for selector in result["selectors"]:
            self.assertEqual(selector["matchCount"], 1)
            self.assertTrue(selector["stable"])
        self.assertIn("com.example:id/login", result["selectors"][0]["expression"])


if __name__ == "__main__":
    unittest.main()
