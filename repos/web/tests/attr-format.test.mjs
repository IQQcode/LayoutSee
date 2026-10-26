// attrFormat 纯函数单测：Lookin 属性值格式化与短码标签映射
import { test } from "node:test";
import assert from "node:assert/strict";

import { attrLabel, formatAttrValue, groupLabel, isCustomClass, sectionLabel } from "../src/features/workbench/tabs/attrFormat.js";

test("formatAttrValue 覆盖契约 extras 的全部值 kind", () => {
  assert.deepEqual(formatAttrValue({ kind: "nil" }), { text: "nil" });
  assert.deepEqual(formatAttrValue({ kind: "boolean", value: true }), { text: "true" });
  assert.deepEqual(formatAttrValue({ kind: "number", value: 3.0 }), { text: "3" });
  assert.deepEqual(formatAttrValue({ kind: "number", value: 721.333333 }), { text: "721.333" });
  assert.deepEqual(formatAttrValue({ kind: "enum", value: 7 }), { text: "7" });
  assert.deepEqual(formatAttrValue({ kind: "string", value: "PackSmart" }), { text: "PackSmart" });
  assert.deepEqual(formatAttrValue({ kind: "rect", x: 61.99, y: 11, width: 103.33, height: 24 }), {
    text: "61.99, 11, 103.33 × 24",
  });
  assert.deepEqual(formatAttrValue({ kind: "point", x: 113.66, y: 23 }), { text: "(113.66, 23)" });
  assert.deepEqual(formatAttrValue({ kind: "size", width: 402, height: 874 }), { text: "402 × 874" });
  assert.deepEqual(formatAttrValue({ kind: "edges", top: 0, left: 1, bottom: 2, right: 3 }), {
    text: "T0 L1 B2 R3",
  });
});

test("formatAttrValue 颜色输出 hex 文本与 CSS 色块", () => {
  const { text, swatch } = formatAttrValue({ kind: "color", rgba: [0.082, 0.396, 0.753, 1.0] });
  assert.equal(text, "#1565C0");
  assert.match(swatch ?? "", /^rgba\(21, 101, 192, 1\)$/);
  // 半透明 alpha 进 hex
  const soft = formatAttrValue({ kind: "color", rgba: [0, 0, 0, 0.5] });
  assert.equal(soft.text, "#00000080");
  assert.equal(formatAttrValue({ kind: "color", rgba: [0, 0, 0, 1] }).text, "#000000");
});

test("formatAttrValue 类链与兜底", () => {
  assert.deepEqual(formatAttrValue({ kind: "chain", value: [["UILabel", "UIView"]] }), { text: "UILabel → UIView" });
  assert.deepEqual(formatAttrValue({ kind: "raw", value: "opaque" }), { text: "opaque" });
  assert.equal(formatAttrValue("plain").text, "plain");
});

test("短码标签映射：已知命中、未知回落", () => {
  assert.equal(groupLabel("l"), "Layout");
  assert.equal(groupLabel("vl"), "视图与图层");
  assert.equal(groupLabel("zz"), "zz");
  assert.equal(sectionLabel("l_f"), "Frame");
  assert.equal(sectionLabel("v_s"), "阴影");
  assert.equal(sectionLabel("unknown_sec"), "unknown_sec");
  assert.equal(attrLabel("vl_i_i"), "userInteractionEnabled");
  assert.equal(attrLabel("lb_t_t"), "text");
  assert.equal(attrLabel("lb_f_n"), "fontName");
  assert.equal(attrLabel("nope_nope"), "nope_nope");
});

test("isCustomClass 区分系统类与业务自定义类", () => {
  assert.equal(isCustomClass("UILabel"), false);
  assert.equal(isCustomClass("NSLayoutAnchor"), false);
  assert.equal(isCustomClass("_UITouchPassthroughView"), false);
  assert.equal(isCustomClass("PSVibeCardView"), true);
  assert.equal(isCustomClass("PSBadgeLabel"), true);
  assert.equal(isCustomClass(""), false);
});
