// 未开放平台（iOS / HarmonyOS）占位面板。
// 动画参考 reactbits 的 BlurText（逐词模糊入场）与 ShinyText（金属光泽扫过），
// 效果本身可纯 CSS 表达，因此不引入 motion/gsap 依赖；同样遵循 prefers-reduced-motion。
import { MorphGlyph, glyphs } from "../../components/MorphIcons.jsx";
import { Button } from "../../components/ui.jsx";

const REVEAL_STEP_MS = 90;
// 长段落用更短的错峰，否则逐词排队会拖到几秒才读完
const DETAIL_STEP_MS = 26;

function BlurWords({ text, step = REVEAL_STEP_MS, className = "" }) {
  const words = String(text).split(" ");
  return (
    <span className={`blur-words ${className}`.trim()}>
      {words.map((word, index) => (
        // 逐词错峰：每个词自己的 animation-delay 造成依次解析的观感
        <span key={`${word}-${index}`} className="blur-word" style={{ animationDelay: `${index * step}ms` }}>
          {word}
        </span>
      ))}
    </span>
  );
}

export function PlatformPlaceholder({ platform, onBackToAndroid }) {
  const { label, headline, note, detail } = platform;
  return (
    <section className="platform-placeholder" aria-live="polite">
      <div className="platform-placeholder-glyph" aria-hidden="true">
        <span className="halo" />
        <MorphGlyph icon={platform.glyph} size={30} strokeWidth={1.6} spring="smooth" />
      </div>

      <h2 className="platform-placeholder-title">
        <BlurWords text={headline} />
      </h2>

      <p className="platform-placeholder-shiny">
        <span className="shiny-text">{note}</span>
      </p>

      <p className="platform-placeholder-detail">
        <BlurWords text={detail} step={DETAIL_STEP_MS} className="blur-words-slow" />
      </p>

      <div className="platform-placeholder-actions">
        <Button compact icon={glyphs.back} onClick={onBackToAndroid}>
          返回 Android
        </Button>
      </div>

      <ul className="platform-placeholder-list">
        <li><span className="dot" aria-hidden="true" />设备发现与接入诊断</li>
        <li><span className="dot" aria-hidden="true" />实时投屏与画面操控</li>
        <li><span className="dot" aria-hidden="true" />原子快照、层级树与元素定位</li>
        <li><span className="dot" aria-hidden="true" />MCP 工具与插件能力</li>
      </ul>
      <p className="platform-placeholder-footnote">以上能力当前仅对 Android 设备开放。</p>
    </section>
  );
}
