import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client.js";
import { HostBridge } from "../../app/HostBridge.js";
import { MorphGlyph, glyphs } from "../../components/MorphIcons.jsx";
import { Button, Dialog } from "../../components/ui.jsx";
import { AGENT_INTRO_LEAD, AGENT_SKILLS } from "./agentSkills.js";

// 兜底标记：settings 写失败（如 Core 重启窗口期）时避免下次启动反复打扰；主标记仍是 settings 键
const SEEN_LOCAL_KEY = "layoutsee.agentIntroSeen";

function readLocalSeen() {
  try {
    return window.localStorage.getItem(SEEN_LOCAL_KEY) === "1";
  } catch {
    return false;
  }
}

function markLocalSeen() {
  try {
    window.localStorage.setItem(SEEN_LOCAL_KEY, "1");
  } catch {
    // 隐私模式等场景写不进就放弃
  }
}

// 首启判定（纯函数，切片测试）：会话可写 + settings 未看过 + 本地无兜底标记，三者同时成立才弹
export function shouldShowIntro(sessionState, settings, localSeen) {
  if (sessionState !== "ready" || localSeen) return false;
  return settings?.agentIntroSeen === false;
}

export function AgentIntroDialog() {
  const [open, setOpen] = useState(false);
  const stateRef = useRef({ sessionState: null, settings: null });

  const evaluate = useCallback(() => {
    setOpen(shouldShowIntro(stateRef.current.sessionState, stateRef.current.settings, readLocalSeen()));
  }, []);

  useEffect(() => {
    let active = true;
    let settingsLoaded = false;
    // KernelBanner 范式：订阅会话状态；no_session（只读观察）不弹，ready 且可写时拉 settings 判定
    const unsubscribe = HostBridge.subscribe((session) => {
      if (!active) return;
      stateRef.current.sessionState = session?.state ?? null;
      if (session?.state === "ready" && !settingsLoaded) {
        settingsLoaded = true;
        api.settings()
          .then((settings) => {
            if (!active) return;
            stateRef.current.settings = settings;
            evaluate();
          })
          .catch(() => {
            // settings 读不到就不弹，避免在异常态打扰
          });
      } else {
        evaluate();
      }
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [evaluate]);

  const dismiss = useCallback(() => {
    setOpen(false);
    markLocalSeen();
    api.saveSettings({ agentIntroSeen: true }).catch(() => {
      // 写失败不重试；本地兜底已保证本次安装不再弹
    });
  }, []);

  return (
    <Dialog
      title="让 AI 读懂你的界面"
      open={open}
      onClose={dismiss}
      footer={<Button variant="primary" onClick={dismiss}>知道了</Button>}
    >
      <p className="intro-lead">
        <MorphGlyph icon={glyphs.sparkles} className="intro-lead-icon" />
        <span>{AGENT_INTRO_LEAD}</span>
      </p>
      <ul className="intro-skills">
        {AGENT_SKILLS.map((skill) => (
          <li key={skill.name} className="intro-skill">
            <span className="agent-skill-icon" aria-hidden="true"><MorphGlyph icon={glyphs[skill.glyph]} size={16} /></span>
            <div className="intro-skill-body">
              <div className="agent-skill-head">
                <code>{skill.name}</code>
                <span className="skill-tag">{skill.tag}</span>
              </div>
              <p>{skill.summary}</p>
            </div>
          </li>
        ))}
      </ul>
      <p className="intro-footnote">把这三个 Skill 交给任意 AI 客户端即可使用；详情见 设置 → Agent。</p>
    </Dialog>
  );
}
