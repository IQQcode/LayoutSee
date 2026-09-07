// Android 日志抓取：所有设备能力都走 $u 桥，插件自身不发网络请求（CSP connect-src 'none'）。
const POLL_MS = 1000;
const PAGE_LIMIT = 800;
const MAX_ENTRIES = 5000;
const MAX_ROWS = 3000;
const LEVEL_ORDER = { V: 0, D: 1, I: 2, W: 3, E: 4, F: 5, S: 6 };
const PREF_KEY = "prefs";

const el = {
  deviceChip: document.getElementById("device-chip"),
  query: document.getElementById("query"),
  caseToggle: document.getElementById("case"),
  level: document.getElementById("level"),
  actions: document.querySelector(".actions"),
  toggle: document.getElementById("toggle"),
  tail: document.getElementById("tail"),
  wrap: document.getElementById("wrap"),
  export: document.getElementById("export"),
  log: document.getElementById("log"),
  rows: document.getElementById("rows"),
  empty: document.getElementById("empty"),
  stateDot: document.getElementById("state-dot"),
  stateText: document.getElementById("state-text"),
  countShown: document.getElementById("count-shown"),
  countTotal: document.getElementById("count-total"),
  hint: document.getElementById("hint"),
};

const state = {
  entries: [],
  cursor: null,
  running: true,
  tail: true,
  wrap: false,
  caseSensitive: false,
  pinned: null,
  readonly: false,
  deviceId: null,
  shown: 0,
  lastShown: false,
  inflight: false,
  timer: null,
  filter: null,
};

/** AS 风格过滤表达式：tag: / -tag: / pid: / level: 与裸文本、-裸文本。 */
function parseQuery(text) {
  const filter = { tags: [], notTags: [], pids: [], words: [], notWords: [], level: null };
  for (const token of String(text || "").trim().split(/\s+/).filter(Boolean)) {
    const negated = token.startsWith("-");
    const body = negated ? token.slice(1) : token;
    const separator = body.indexOf(":");
    const key = separator > 0 ? body.slice(0, separator).toLowerCase() : "";
    const value = separator > 0 ? body.slice(separator + 1) : body;
    if (!value) continue;
    if (key === "tag") (negated ? filter.notTags : filter.tags).push(value);
    else if (key === "pid") filter.pids.push(value);
    else if (key === "level") filter.level = value.slice(0, 1).toUpperCase();
    else if (key === "message" || key === "msg") (negated ? filter.notWords : filter.words).push(value);
    else (negated ? filter.notWords : filter.words).push(body);
  }
  return filter;
}

function fold(text) {
  return state.caseSensitive ? text : String(text).toLowerCase();
}

function hit(haystack, needle) {
  return fold(haystack).includes(fold(needle));
}

/** 命中判定。续行（堆栈）跟随上一条被显示的记录，否则堆栈会被文本过滤切断。 */
function shouldShow(entry) {
  if (entry.continuation) return state.lastShown;
  const filter = state.filter;
  const floor = LEVEL_ORDER[filter.level ?? state.level] ?? 0;
  if ((LEVEL_ORDER[entry.level] ?? 0) < floor) return false;
  if (filter.pids.length && !filter.pids.includes(String(entry.pid))) return false;
  if (filter.tags.length && !filter.tags.some((tag) => hit(entry.tag, tag))) return false;
  if (filter.notTags.some((tag) => hit(entry.tag, tag))) return false;
  const line = `${entry.tag} ${entry.message}`;
  if (filter.words.length && !filter.words.every((word) => hit(line, word))) return false;
  if (filter.notWords.some((word) => hit(line, word))) return false;
  return true;
}

function rowFor(entry) {
  const row = document.createElement("div");
  row.className = `row lvl-${entry.level}${entry.continuation ? " cont" : ""}`;
  row.dataset.seq = String(entry.seq);
  if (state.pinned === entry.seq) row.classList.add("is-pinned");
  const cells = [
    ["time", entry.time],
    ["ids", `${entry.pid}-${entry.tid}`],
    ["level", entry.level],
    ["tag", entry.tag],
    ["message", entry.message],
  ];
  for (const [className, value] of cells) {
    const cell = document.createElement("span");
    cell.className = className;
    cell.textContent = value;
    row.append(cell);
  }
  return row;
}

function trimRows() {
  while (el.rows.childElementCount > MAX_ROWS) el.rows.removeChild(el.rows.firstChild);
}

function updateCounters() {
  el.countShown.textContent = String(state.shown);
  el.countTotal.textContent = String(state.entries.length);
  el.empty.hidden = state.shown > 0;
  el.empty.textContent = state.entries.length ? "没有匹配当前过滤条件的日志" : "暂无日志，设备产生新日志后会自动出现";
}

function appendEntries(entries) {
  const fragment = document.createDocumentFragment();
  for (const entry of entries) {
    const visible = shouldShow(entry);
    state.lastShown = entry.continuation ? state.lastShown : visible;
    if (!visible) continue;
    fragment.append(rowFor(entry));
    state.shown += 1;
  }
  if (fragment.childElementCount) {
    el.rows.append(fragment);
    trimRows();
    if (state.tail) el.log.scrollTop = el.log.scrollHeight;
  }
  updateCounters();
}

function rerender() {
  el.rows.replaceChildren();
  state.shown = 0;
  state.lastShown = false;
  appendEntries(state.entries);
  if (state.tail) el.log.scrollTop = el.log.scrollHeight;
}

function setHint(text, tone) {
  el.hint.textContent = text || "";
  el.hint.classList.toggle("error", tone === "error");
}

function setRunning(running) {
  state.running = running;
  document.body.classList.toggle("is-paused", !running);
  el.toggle.setAttribute("aria-pressed", running ? "false" : "true");
  el.toggle.title = running ? "暂停抓取（pause logcat）" : "继续抓取（resume logcat）";
  el.stateDot.className = `dot ${running ? "running" : "paused"}`;
  el.stateText.textContent = running ? "抓取中" : "已暂停";
  if (running) schedule(0);
}

function setTail(tail) {
  state.tail = tail;
  el.tail.setAttribute("aria-pressed", tail ? "true" : "false");
  if (tail) {
    state.pinned = null;
    el.rows.querySelectorAll(".row.is-pinned").forEach((row) => row.classList.remove("is-pinned"));
    el.log.scrollTop = el.log.scrollHeight;
  }
}

function resetBuffer() {
  state.entries = [];
  state.cursor = null;
  state.pinned = null;
  rerender();
}

function schedule(delay) {
  window.clearTimeout(state.timer);
  state.timer = window.setTimeout(poll, delay ?? POLL_MS);
}

async function poll() {
  if (!state.running || state.inflight || document.hidden) {
    schedule();
    return;
  }
  state.inflight = true;
  try {
    const payload = await $u.device.logcat({ after: state.cursor, limit: PAGE_LIMIT });
    // Core 侧游标比本地新只可能是日志被清空过，直接重置本地缓冲
    if (payload.reset) resetBuffer();
    state.cursor = payload.cursor;
    if (payload.lines.length) {
      state.entries.push(...payload.lines);
      if (state.entries.length > MAX_ENTRIES) state.entries.splice(0, state.entries.length - MAX_ENTRIES);
      appendEntries(payload.lines);
    }
    setHint(payload.dropped ? "设备日志缓冲已滚过，中间有日志未能抓取" : "");
    el.stateDot.className = state.running ? "dot running" : "dot paused";
  } catch (error) {
    el.stateDot.className = "dot error";
    setHint(`读取失败：${error.message}`, "error");
  } finally {
    state.inflight = false;
    schedule();
  }
}

let prefTimer = null;
function savePrefs() {
  window.clearTimeout(prefTimer);
  prefTimer = window.setTimeout(() => {
    const prefs = { level: state.level, query: el.query.value, wrap: state.wrap, caseSensitive: state.caseSensitive };
    $u.storage.set(PREF_KEY, JSON.stringify(prefs)).catch(() => {});
  }, 400);
}

function applyFilter() {
  state.level = el.level.value;
  state.filter = parseQuery(el.query.value);
  rerender();
  savePrefs();
}

async function clearLogcat() {
  try {
    await $u.device.logcatClear();
    resetBuffer();
    setHint("");
    await $u.ui.toast("设备日志已清空");
  } catch (error) {
    setHint(`清空失败：${error.message}`, "error");
  }
}

el.query.addEventListener("input", applyFilter);
el.level.addEventListener("change", applyFilter);

el.caseToggle.addEventListener("click", () => {
  state.caseSensitive = !state.caseSensitive;
  el.caseToggle.setAttribute("aria-pressed", state.caseSensitive ? "true" : "false");
  applyFilter();
});

el.actions.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  switch (button.dataset.action) {
    case "clear":
      await clearLogcat();
      return;
    case "toggle":
      setRunning(!state.running);
      return;
    case "restart":
      await clearLogcat();
      setRunning(true);
      setTail(true);
      return;
    case "tail":
      setTail(true);
      return;
    case "wrap":
      state.wrap = !state.wrap;
      el.rows.classList.toggle("wrap", state.wrap);
      el.log.classList.toggle("wrap", state.wrap);
      el.wrap.setAttribute("aria-pressed", state.wrap ? "true" : "false");
      savePrefs();
      return;
    case "export": {
      const text = [...el.rows.children].map((row) => [...row.children].map((cell) => cell.textContent).join(" ")).join("\n");
      if (!text) {
        await $u.ui.toast("当前没有可导出的日志", "danger");
        return;
      }
      const name = `logcat-${state.deviceId ?? "device"}-${state.entries.length}.log`;
      try {
        await $u.host.saveFile(name, text);
        await $u.ui.toast("日志已导出");
      } catch {
        // 宿主没有保存能力（浏览器）时降级为复制
        await $u.host.copyText(text);
        await $u.ui.toast("当前宿主不支持保存文件，已改为复制", "danger");
      }
      return;
    }
    default:
      return;
  }
});

// 点击某一行停止自动滚动并保持该行可见，与 Android Studio 一致
el.rows.addEventListener("click", (event) => {
  const row = event.target.closest(".row");
  if (!row) return;
  el.rows.querySelectorAll(".row.is-pinned").forEach((item) => item.classList.remove("is-pinned"));
  row.classList.add("is-pinned");
  state.pinned = Number(row.dataset.seq);
  setTail(false);
});

el.log.addEventListener("scroll", () => {
  const atBottom = el.log.scrollHeight - el.log.scrollTop - el.log.clientHeight < 24;
  if (atBottom !== state.tail) {
    state.tail = atBottom;
    el.tail.setAttribute("aria-pressed", atBottom ? "true" : "false");
  }
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && state.running) schedule(0);
});

function applyContext(context) {
  state.readonly = Boolean(context.readonly);
  document.documentElement.dataset.theme = context.theme === "dark" ? "dark" : "light";
  if (context.deviceId && context.deviceId !== state.deviceId) {
    state.deviceId = context.deviceId;
    el.deviceChip.textContent = context.deviceId;
    el.deviceChip.title = context.deviceId;
    resetBuffer();
  }
  const clearButton = el.actions.querySelector('button[data-action="clear"]');
  const restartButton = el.actions.querySelector('button[data-action="restart"]');
  for (const button of [clearButton, restartButton]) {
    button.disabled = state.readonly;
    button.title = state.readonly ? "只读模式下不能清空设备日志" : button.getAttribute("aria-label");
  }
}

async function boot() {
  try {
    const stored = await $u.storage.get(PREF_KEY);
    const prefs = stored?.value ? JSON.parse(stored.value) : {};
    if (prefs.level) el.level.value = prefs.level;
    if (prefs.query) el.query.value = prefs.query;
    state.caseSensitive = Boolean(prefs.caseSensitive);
    el.caseToggle.setAttribute("aria-pressed", state.caseSensitive ? "true" : "false");
    if (prefs.wrap) {
      state.wrap = true;
      el.rows.classList.add("wrap");
      el.wrap.setAttribute("aria-pressed", "true");
    }
  } catch {
    // 首次使用或存储被拒绝：用默认配置继续
  }
  state.level = el.level.value;
  state.filter = parseQuery(el.query.value);
  setTail(true);
  setRunning(true);
  try {
    applyContext(await $u.host.getContext());
  } catch (error) {
    setHint(`无法连接宿主桥：${error.message}`, "error");
  }
  $u.on("context.changed", (payload) => applyContext(payload || {}));
}

boot();
