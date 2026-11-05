// 首启弹窗决策纯函数与 Agent 能力展示数据单测
// AgentIntroDialog.jsx 是 JSX，按仓库惯例只截取纯函数片段执行；agentSkills.js 是纯 ESM 可直接 import
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { AGENT_INTRO_LEAD, AGENT_SKILLS } from "../src/features/onboarding/agentSkills.js";

const here = dirname(fileURLToPath(import.meta.url));

function loadShouldShowIntro() {
  const source = readFileSync(join(here, "../src/features/onboarding/AgentIntroDialog.jsx"), "utf8");
  // 从 "function" 起切，跳过 export 关键字（new Function 不接受 export 声明）
  const start = source.indexOf("function shouldShowIntro");
  const block = source.slice(start, source.indexOf("\n}\n", start) + 3);
  return new Function(`${block}; return { shouldShowIntro };`)();
}

test("首启弹窗只在 会话可写 + settings 未看过 + 无本地兜底 时弹出", () => {
  const { shouldShowIntro } = loadShouldShowIntro();
  assert.equal(shouldShowIntro("ready", { agentIntroSeen: false }, false), true);
  assert.equal(shouldShowIntro("no_session", { agentIntroSeen: false }, false), false, "只读观察模式不弹");
  assert.equal(shouldShowIntro("starting", { agentIntroSeen: false }, false), false, "会话未就绪不弹");
  assert.equal(shouldShowIntro("ready", { agentIntroSeen: true }, false), false, "已看过不再弹");
  assert.equal(shouldShowIntro("ready", { agentIntroSeen: false }, true), false, "本地兜底标记生效");
  assert.equal(shouldShowIntro("ready", null, false), false, "settings 未加载不弹");
  assert.equal(shouldShowIntro("ready", {}, false), false, "旧 settings 无该键（合并前）不弹");
});

test("Agent 能力展示数据：三个 skill，文案与提示词齐全", () => {
  assert.equal(AGENT_SKILLS.length, 3);
  assert.deepEqual(AGENT_SKILLS.map((skill) => skill.name), ["layout-see", "layout-env", "layout-lookin-server"]);
  for (const skill of AGENT_SKILLS) {
    assert.ok(skill.glyph, "每个 skill 都有图标键");
    assert.ok(skill.tag && skill.summary, "tag 与 summary 非空");
    assert.ok(skill.prompt.startsWith(`用 ${skill.name}`), "示例提示词以 skill 名开头");
  }
  assert.match(AGENT_INTRO_LEAD, /12 个工具/);
});
