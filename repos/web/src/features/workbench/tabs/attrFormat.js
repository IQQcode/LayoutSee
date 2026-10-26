// Lookin 属性短码 → 展示语义（纯函数，供 ElementTab 属性面板使用）。
// 短码事实源：LookinServer LookinAttrIdentifiers.m（MIT），常量名尾段即语义；
// 常用属性在 ATTR_LABEL_OVERRIDES 里用 API 名覆盖自动命名，未识别的回落短码本身。

export const GROUP_LABELS = {
  n: "基础",
  c: "Class",
  r: "Relation",
  l: "Layout",
  a: "Auto Layout",
  vl: "视图与图层",
  i: "UIImageView",
  la: "UILabel",
  co: "UIControl",
  b: "UIButton",
  s: "UIScrollView",
  ta: "UITableView",
  te: "UITextView",
  tf: "UITextField",
  ve: "UIVisualEffectView",
  UIStackView: "UIStackView",
  guc: "自定义属性",
};

export const SECTION_LABELS = {
  n: "",
  sec_ctm: "自定义",
  cl_c: "Class",
  r_r: "Relation",
  l_f: "Frame",
  l_b: "Bounds",
  l_s: "Safe Area",
  l_p: "Position",
  l_a: "Anchor Point",
  a_h: "Content Hugging",
  a_r: "Content Compression Resistance",
  a_c: "Constraints",
  a_i: "Intrinsic Size",
  v_v: "显示",
  v_i: "交互",
  v_c: "圆角",
  v_b: "背景",
  v_bo: "边框",
  v_s: "阴影",
  v_co: "Content Mode",
  v_t: "Tint",
  v_ta: "Tag",
  i_n: "名称",
  i_o: "打开",
  lb_t: "Text",
  lb_f: "Font",
  lb_n: "行数",
  lb_tc: "Text Color",
  lb_b: "换行",
  lb_a: "对齐",
  lb_c: "自适应字号",
  c_e: "状态",
  c_v: "垂直对齐",
  c_h: "水平对齐",
  c_o: "外边距",
  b_c: "Content Insets",
  b_t: "Title Insets",
  b_i: "Image Insets",
  s_c: "Content Inset",
  s_a: "Adjusted Inset",
  s_i: "Indicator Inset",
  s_o: "Offset",
  s_cs: "Content Size",
  s_b: "Behavior",
  s_si: "滚动条",
  s_bo: "Bounce",
  s_s: "Scroll & Paging",
  s_ct: "Content Touches",
  s_z: "Zoom",
  s_ii: "Initial Inset",
  t_s: "Style",
  t_sn: "Sections",
  t_r: "Rows",
  t_ss: "Separator Style",
  t_sc: "Separator Color",
  t_si: "Separator Inset",
  tv_b: "基础",
  tv_t: "Text",
  tv_f: "Font",
  tv_tc: "Text Color",
  tv_a: "对齐",
  tv_c: "Container Inset",
  tf_t: "Text",
  tf_p: "Placeholder",
  tf_f: "Font",
  tf_tc: "Text Color",
  tf_a: "对齐",
  tf_c: "清除",
  tf_ca: "自适应字号",
  tf_cb: "Clear Button",
  ve_s: "Style",
  ve_f: "前景色",
  usv_axis: "Axis",
  usv_dis: "Distribution",
  usv_align: "Alignment",
  usv_spa: "Spacing",
};

const AUTO_ATTR_LABELS = {
  n: "none", ctm: "custom", c_c_c: "classChain", r_r_r: "ivarRelation",
  l_f_f: "frame", l_b_b: "bounds", l_s_s: "safeAreaInsets", l_p_p: "position", l_a_a: "anchorPoint",
  al_h_h: "horizontal", al_h_v: "vertical", al_r_h: "horizontal", al_r_v: "vertical", al_c_c: "constraints", cl_i_s: "intrinsicSize",
  vl_v_h: "hidden", vl_v_o: "opacity", vl_i_i: "userInteractionEnabled", vl_i_m: "masksToBounds",
  vl_c_r: "cornerRadius", vl_b_b: "backgroundColor", vl_b_c: "borderColor", vl_b_w: "borderWidth",
  vl_s_c: "shadowColor", vl_s_o: "shadowOpacity", vl_s_r: "shadowRadius", vl_s_ow: "shadowOffsetX", vl_s_oh: "shadowOffsetY",
  vl_c_m: "contentMode", vl_t_c: "tintColor", vl_t_m: "tintAdjustmentMode", vl_t_t: "tag",
  iv_n_n: "imageName", iv_o_o: "highlighted", lb_t_t: "text", lb_f_n: "fontName", lb_f_s: "fontSize",
  lb_n_n: "numberOfLines", lb_t_c: "textColor", lb_a_a: "textAlignment", lb_b_m: "lineBreakMode", lb_c_c: "adjustsFontSizeToFit",
  ct_e_e: "enabled", ct_e_s: "selected", ct_v_a: "verticalAlignment", ct_h_a: "contentHorizontalAlignment", ct_o_e: "contentEdgeInsets",
  bt_c_i: "contentEdgeInsets", bt_t_i: "titleEdgeInsets", bt_i_i: "imageEdgeInsets",
  sv_o_o: "contentOffset", sv_c_s: "contentSize", sv_c_i: "contentInset", sv_a_i: "adjustedContentInset",
  sv_b_b: "bounces", sv_i_i: "indicatorInsets", sv_s_s: "scrollEnabled", sv_s_p: "pagingEnabled",
  sv_b_v: "alwaysBounceVertical", sv_b_h: "alwaysBounceHorizontal", sv_h_h: "showsHorizontalScrollIndicator",
  sv_s_v: "showsVerticalScrollIndicator", sv_c_d: "delaysContentTouches", sv_c_c: "canCancelContentTouches",
  sv_z_mi: "minimumZoomScale", sv_z_ma: "maximumZoomScale", sv_z_s: "zoomScale", sv_z_b: "bouncesZoom", sv_qi_i: "qmui_initialInset",
  tv_s_s: "style", tv_s_n: "numberOfSections", tv_r_n: "numberOfRows", tv_s_i: "separatorInset",
  tv_s_c: "separatorColor", tv_ss_s: "separatorStyle",
  te_f_n: "fontName", te_f_s: "fontSize", te_b_e: "editable", te_b_s: "selectable",
  te_t_t: "text", te_t_c: "textColor", te_a_a: "textAlignment", te_c_i: "contentInset",
  tf_t_t: "text", tf_p_p: "placeholder", tf_f_n: "fontName", tf_f_s: "fontSize", tf_t_c: "textColor",
  tf_a_a: "textAlignment", tf_c_c: "clearsOnBeginEditing", tf_c_co: "clearsOnInsertion",
  tf_c_ca: "adjustsFontSizeToFit", tf_c_m: "minimumFontSize", tf_cb_m: "clearButtonMode",
  ve_s_s: "style", ve_f_c: "foregroundColor",
  usv_axis_axis: "axis", usv_dis_dis: "distribution", usv_ali_ali: "alignment", usv_spa_spa: "spacing",
};

export function groupLabel(identifier) {
  return GROUP_LABELS[identifier] ?? identifier;
}

export function sectionLabel(identifier) {
  return SECTION_LABELS[identifier] ?? identifier;
}

export function attrLabel(identifier) {
  return AUTO_ATTR_LABELS[identifier] ?? identifier;
}

const round3 = (value) => {
  const rounded = Math.round(value * 1000) / 1000;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
};

const rgbaToCss = (rgba) => {
  const [r, g, b, a] = rgba.map((item) => Math.min(1, Math.max(0, item)));
  return `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, ${Math.round(a * 1000) / 1000})`;
};

const rgbaToHex = (rgba) => {
  const byte = (item) => Math.round(Math.min(1, Math.max(0, item)) * 255).toString(16).padStart(2, "0");
  return `#${rgba.slice(0, 3).map(byte).join("")}${rgba[3] < 1 ? byte(rgba[3]) : ""}`.toUpperCase();
};

// 值 → { text, swatch }：swatch 为 CSS 色值（仅 color 类），text 供面板展示
export function formatAttrValue(value) {
  if (!value || typeof value !== "object") return { text: String(value ?? "") };
  switch (value.kind) {
    case "nil":
      return { text: "nil" };
    case "boolean":
      return { text: value.value ? "true" : "false" };
    case "number":
      return { text: round3(value.value) };
    case "enum":
      return { text: `${value.value}` };
    case "string":
      return { text: value.value };
    case "color": {
      const rgba = Array.isArray(value.rgba) && value.rgba.length === 4 ? value.rgba : [0, 0, 0, 0];
      return { text: rgbaToHex(rgba), swatch: rgbaToCss(rgba) };
    }
    case "rect":
      return { text: `${round3(value.x)}, ${round3(value.y)}, ${round3(value.width)} × ${round3(value.height)}` };
    case "point":
      return { text: `(${round3(value.x)}, ${round3(value.y)})` };
    case "size":
      return { text: `${round3(value.width)} × ${round3(value.height)}` };
    case "edges":
      return { text: `T${round3(value.top)} L${round3(value.left)} B${round3(value.bottom)} R${round3(value.right)}` };
    case "chain": {
      const rows = Array.isArray(value.value) ? value.value : [];
      const first = rows[0];
      return { text: Array.isArray(first) ? first.join(" → ") : rows.join(" → ") };
    }
    default:
      return { text: String(value.value ?? "") };
  }
}

// 非 UIKit 系统前缀（UI/NS/_UI/_NS）视为业务自定义类，树中高亮
export function isCustomClass(className) {
  return typeof className === "string" && className.length > 0 && !/^(UI|NS|_UI|_NS|CF|CA)/.test(className);
}
