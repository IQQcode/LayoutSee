// Agent 能力展示共享数据：首启弹窗与设置「Agent」分区共用，改文案两处同步生效。
// glyph 存 MorphIcons.jsx 里 glyphs 的键名而非图标本体，保证本文件可被纯函数测试直接切片执行。
export const AGENT_INTRO_LEAD =
  "LayoutSee 把设备运行时视图树交给 AI——控件是什么、在哪、多大、能不能点，都有结构依据。MCP 已内置 12 个工具（9 读 3 写），随设备开箱即用。";

export const AGENT_SKILLS = Object.freeze([
  {
    glyph: "scanEye",
    name: "layout-see",
    tag: "布局感知",
    summary: "抓取真机/模拟器视图树，定位控件、诊断重叠遮挡与点击热区",
    prompt: "用 layout-see 读取当前设备页面，列出可点击元素及其 resource-id。",
  },
  {
    glyph: "wrench",
    name: "layout-env",
    tag: "一键配置",
    summary: "自动探测与映射 ADB 路径，体检 Android / iOS 两端环境",
    prompt: "用 layout-env 帮我做 LayoutSee 的环境体检与一键配置。",
  },
  {
    glyph: "smartphone",
    name: "layout-lookin-server",
    tag: "iOS 接入",
    summary: "自动把 LookinServer 集成进你的 iOS 工程",
    prompt: "用 layout-lookin-server 把 LookinServer 集成进我的 iOS 工程。",
  },
]);
