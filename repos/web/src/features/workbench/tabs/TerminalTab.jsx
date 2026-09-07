import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Broom, Terminal } from "@phosphor-icons/react";
import { api } from "../../../api/client.js";
import { LogTags, uiLog } from "../../../api/logger.js";
import { Banner, Button, CopyButton, Dialog, StatusPill } from "../../../components/ui.jsx";

const HISTORY_LIMIT = 100;
const OUTPUT_LIMIT = 50;
const TIMEOUT_OPTIONS = [
  { value: 15_000, label: "15 秒" },
  { value: 30_000, label: "30 秒" },
  { value: 60_000, label: "60 秒" },
];

// 高危命令前缀：命中后必须二次确认。判定基于去掉多余空格后的小写命令串
const RISKY_PATTERNS = [
  { pattern: /^rm\s|\srm\s+-[rf]/, reason: "删除设备文件" },
  { pattern: /^pm\s+(uninstall|clear|disable)/, reason: "卸载/清空/禁用应用" },
  { pattern: /^(reboot|svc\s+power|shutdown)/, reason: "重启或断电设备" },
  { pattern: /^(dd|mkfs|wipe|fastboot)/, reason: "写入或擦除存储" },
  { pattern: /^settings\s+put/, reason: "修改系统设置" },
  { pattern: /^(am\s+force-stop|killall|kill\s+-9)/, reason: "强制结束进程" },
  { pattern: /^su\b|^setenforce/, reason: "提权或改变安全策略" },
];

function historyKey(deviceId) {
  return `layoutsee.terminal.history.${deviceId}`;
}

function readHistory(deviceId) {
  try {
    const raw = JSON.parse(localStorage.getItem(historyKey(deviceId)) ?? "[]");
    return Array.isArray(raw) ? raw.filter((item) => typeof item === "string").slice(0, HISTORY_LIMIT) : [];
  } catch {
    return [];
  }
}

function riskOf(command) {
  const normalized = command.trim().toLowerCase().replace(/\s+/g, " ");
  return RISKY_PATTERNS.find((item) => item.pattern.test(normalized)) ?? null;
}

// 历史去重后置顶并裁到上限；纯函数便于单测环形行为
function mergeHistory(list, value) {
  return [value, ...list.filter((item) => item !== value)].slice(0, HISTORY_LIMIT);
}

export function TerminalTab({ deviceId, readonly, onToast }) {
  const [command, setCommand] = useState("");
  const [timeoutMs, setTimeoutMs] = useState(TIMEOUT_OPTIONS[0].value);
  const [history, setHistory] = useState(() => readHistory(deviceId));
  const [historyCursor, setHistoryCursor] = useState(-1);
  const [entries, setEntries] = useState([]);
  const [running, setRunning] = useState(false);
  const [pending, setPending] = useState(null);
  const outputRef = useRef(null);
  const inputRef = useRef(null);

  // 历史按设备隔离：切设备时重新读取，避免把 A 机的命令补全到 B 机
  useEffect(() => {
    setHistory(readHistory(deviceId));
    setHistoryCursor(-1);
    setEntries([]);
  }, [deviceId]);

  useEffect(() => {
    const node = outputRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [entries]);

  const pushHistory = useCallback((value) => {
    setHistory((current) => {
      const next = mergeHistory(current, value);
      try {
        localStorage.setItem(historyKey(deviceId), JSON.stringify(next));
      } catch {
        // 隐私模式下 localStorage 可能不可写，历史退化为内存态即可
      }
      return next;
    });
    setHistoryCursor(-1);
  }, [deviceId]);

  const execute = useCallback(async (value) => {
    setRunning(true);
    const started = Date.now();
    try {
      const payload = await api.shell(deviceId, value, timeoutMs);
      uiLog(LogTags.common, "终端命令完成", payload.exitCode === 0 ? "info" : "warn", `exit=${payload.exitCode} · ${payload.durationMs}ms`);
      setEntries((current) => [...current, {
        id: `${started}-${current.length}`,
        command: value,
        exitCode: payload.exitCode,
        stdout: payload.stdout,
        stderr: payload.stderr,
        truncated: payload.truncated,
        durationMs: payload.durationMs,
      }].slice(-OUTPUT_LIMIT));
    } catch (error) {
      uiLog(LogTags.common, "终端命令失败", "error", error.message);
      setEntries((current) => [...current, {
        id: `${started}-${current.length}`,
        command: value,
        error: error.message,
      }].slice(-OUTPUT_LIMIT));
      onToast?.(error.message, "danger");
    } finally {
      setRunning(false);
      inputRef.current?.focus();
    }
  }, [deviceId, timeoutMs, onToast]);

  const submit = useCallback(() => {
    const value = command.trim();
    if (!value) return;
    if (readonly) {
      onToast?.("只读模式下终端不可执行命令", "warning");
      return;
    }
    pushHistory(value);
    setCommand("");
    const risk = riskOf(value);
    if (risk) {
      setPending({ command: value, reason: risk.reason });
      return;
    }
    void execute(value);
  }, [command, readonly, onToast, pushHistory, execute]);

  const onKeyDown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submit();
      return;
    }
    if (event.key === "l" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      setEntries([]);
      return;
    }
    if (event.key === "ArrowUp") {
      if (!history.length) return;
      event.preventDefault();
      const next = Math.min(historyCursor + 1, history.length - 1);
      setHistoryCursor(next);
      setCommand(history[next]);
      return;
    }
    if (event.key === "ArrowDown") {
      if (historyCursor < 0) return;
      event.preventDefault();
      const next = historyCursor - 1;
      setHistoryCursor(next);
      setCommand(next < 0 ? "" : history[next]);
    }
  };

  const transcript = useMemo(
    () => entries.map((entry) => `$ ${entry.command}\n${entry.error ?? [entry.stdout, entry.stderr].filter(Boolean).join("")}`).join("\n"),
    [entries],
  );

  return (
    <div className="panel-scroll">
      <div className="panel-title">
        <div>
          <h2>终端</h2>
          <p>命令整串交给 adb shell 执行；上下键翻历史，Ctrl/Cmd+L 清屏</p>
        </div>
        <div className="panel-actions">
          <CopyButton value={transcript} label="复制全部输出" />
          <Button compact icon={Broom} onClick={() => setEntries([])}>清屏</Button>
        </div>
      </div>

      {readonly ? <Banner tone="warning">设备处于只读模式，终端命令会被 Core 拦截。关闭只读模式后才能执行。</Banner> : null}

      <section className="content-card">
        <div className="terminal-output" ref={outputRef} role="log" aria-label="终端输出" tabIndex={0}>
          {entries.length === 0 ? <div className="terminal-empty">还没有执行任何命令。试试 <code>getprop ro.product.model</code>。</div> : null}
          {entries.map((entry) => (
            <div key={entry.id} className="terminal-entry">
              <div className="terminal-command">
                <span className="terminal-prompt">$</span>
                <span className="mono">{entry.command}</span>
                {entry.error ? <StatusPill tone="danger">失败</StatusPill> : (
                  <>
                    <StatusPill tone={entry.exitCode === 0 ? "success" : "warning"}>exit {entry.exitCode}</StatusPill>
                    <span className="terminal-meta">{entry.durationMs}ms</span>
                    {entry.truncated ? <span className="terminal-meta">输出已截断至 256KB</span> : null}
                  </>
                )}
              </div>
              {entry.error ? <pre className="terminal-stderr">{entry.error}</pre> : null}
              {entry.stdout ? <pre>{entry.stdout}</pre> : null}
              {entry.stderr ? <pre className="terminal-stderr">{entry.stderr}</pre> : null}
            </div>
          ))}
        </div>
        <div className="terminal-input-row">
          <span className="terminal-prompt">$</span>
          <input
            ref={inputRef}
            value={command}
            onChange={(event) => { setCommand(event.target.value); setHistoryCursor(-1); }}
            onKeyDown={onKeyDown}
            placeholder="输入 adb shell 命令，回车执行"
            aria-label="终端命令输入"
            spellCheck={false}
            autoComplete="off"
            disabled={running}
          />
          <select value={timeoutMs} onChange={(event) => setTimeoutMs(Number(event.target.value))} aria-label="命令超时">
            {TIMEOUT_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <Button variant="primary" icon={Terminal} loading={running} disabled={readonly || running} onClick={submit}>执行</Button>
        </div>
      </section>

      <Dialog
        title="确认执行高危命令"
        open={Boolean(pending)}
        onClose={() => { setPending(null); inputRef.current?.focus(); }}
        footer={
          <>
            <Button onClick={() => { setPending(null); inputRef.current?.focus(); }}>取消</Button>
            <Button variant="danger" onClick={() => { const target = pending; setPending(null); void execute(target.command); }}>确认执行</Button>
          </>
        }
      >
        <p style={{ margin: 0, lineHeight: 1.7 }}>
          <code>{pending?.command}</code> 可能会{pending?.reason}，结果不可撤销。确定要在设备上执行吗？
        </p>
      </Dialog>
    </div>
  );
}
