from __future__ import annotations

import unittest

from layoutsee_core.errors import CoreError
from layoutsee_core.snapshots import normalize_nodes
from layoutsee_core.xpath import query_record, validate_expression

XML = """<hierarchy rotation="0">
  <node index="0" text="root" resource-id="com.example:id/root" class="android.widget.FrameLayout" package="com.example" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1080,2400]" displayed="true">
    <node index="0" text="登录" resource-id="com.example:id/login" class="android.widget.Button" package="com.example" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[96,300][984,432]" displayed="true"/>
    <node index="1" text="取消" resource-id="" class="android.widget.Button" package="com.example" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[96,500][984,632]" displayed="true"/>
  </node>
</hierarchy>"""


def make_record():
    nodes, elements, element_to_key = normalize_nodes(XML, {"width": 1080, "height": 2400})
    return {"snapshot": {"nodes": nodes}, "elements": elements, "element_to_key": element_to_key, "refs": {}}


class XPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.record = make_record()

    def test_query_maps_results_to_node_keys(self) -> None:
        result = query_record(self.record, "//android.widget.Button")
        self.assertEqual(result["matchCount"], 2)
        self.assertEqual(result["nodeKeys"], ["0.0", "0.1"])

    def test_invalid_expressions_are_rejected_before_execution(self) -> None:
        for expression in ("", "///", "//*[", "unknown-function()"):
            with self.assertRaises(CoreError) as context:
                validate_expression(expression)
            self.assertEqual(context.exception.code, "INVALID_XPATH")

    def test_expression_length_is_limited(self) -> None:
        with self.assertRaises(CoreError) as context:
            validate_expression("//*" + "[@x='a']" * 100)
        self.assertEqual(context.exception.code, "INVALID_XPATH")

    def test_zero_hits_preserves_empty_result(self) -> None:
        result = query_record(self.record, "//android.widget.EditText")
        self.assertEqual(result["matchCount"], 0)
        self.assertEqual(result["nodeKeys"], [])


if __name__ == "__main__":
    unittest.main()
