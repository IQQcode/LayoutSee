// 工作台图标：morphicons（MIT）+ Lucide 描边图标数据。
// MorphIcon 的 icon prop 变化时自动做弹性变形，因此「状态切换」只需换数据。
// 图标数据来自 `lucide`（数据，不是组件）——morphicons 要求描边中心线图标集。
import { MorphIcon } from "morphicons/react";
import {
  Apple, ArrowLeft, Blocks, Camera, CircleCheck, Code, CodeXml, Cog, Crosshair,
  Grid2x2Check, Hexagon, House, Layers, LayoutDashboard, LayoutGrid, LoaderCircle,
  Lock, LockOpen, MousePointerClick, Plug, PlugZap, Power, Puzzle, RotateCcw,
  RotateCw, Settings, Settings2, Smartphone, SmartphoneCharging, Snowflake,
  Sparkle, Sparkles, Sun, Volume1, Volume2,
} from "lucide";

// 控制轨与 Tab 用到的图标数据，集中导出避免散落
export const glyphs = Object.freeze({
  back: ArrowLeft,
  home: House,
  recents: Layers,
  power: Power,
  volumeUp: Volume2,
  volumeDown: Volume1,
  volumeLow: Volume1,
  rotateCw: RotateCw,
  rotateCcw: RotateCcw,
  capture: Camera,
  captureBusy: LoaderCircle,
  captureDone: CircleCheck,
  freeze: Snowflake,
  thaw: Sun,
  locked: Lock,
  unlocked: LockOpen,
  inspect: Crosshair,
  browse: MousePointerClick,
  tabCommon: LayoutGrid,
  tabCommonActive: LayoutDashboard,
  tabElement: Code,
  tabElementActive: CodeXml,
  tabMcp: Plug,
  tabMcpActive: PlugZap,
  tabPlugins: Puzzle,
  tabPluginsActive: Blocks,
  tabIntelligence: Sparkle,
  tabIntelligenceActive: Sparkles,
  navDevices: Smartphone,
  navDevicesActive: SmartphoneCharging,
  navGroup: LayoutGrid,
  navGroupActive: Grid2x2Check,
  navSettings: Cog,
  navSettingsActive: Settings2,
  navSettingsGhost: Settings,
  platformIos: Apple,
  platformHarmony: Hexagon,
});

export { MorphIcon };

/**
 * 统一封装：固定尺寸/线宽/降级策略，调用点只关心 icon。
 * reducedMotion="user" 跟随系统「减弱动态效果」，与设计规范一致。
 */
export function MorphGlyph({ icon, size = 19, strokeWidth = 2, spring = "snappy", spinning = false, className = "", ...rest }) {
  return (
    <MorphIcon
      icon={icon}
      size={size}
      strokeWidth={strokeWidth}
      spring={spring}
      reducedMotion="user"
      className={`morph-glyph ${spinning ? "is-spinning" : ""} ${className}`.trim()}
      {...rest}
    />
  );
}
