// 内置示例插件：验证 $u 桥的上下文、快照读取与宿主能力降级路径。
const statusEl = document.getElementById("status");
const statsEl = document.getElementById("stats");
const exportButton = document.getElementById("export");

let lastSummary = null;

function render(rows) {
  statsEl.innerHTML = "";
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    statsEl.append(dt, dd);
  }
}

function summarize(snapshot) {
  const nodes = snapshot?.nodes ?? [];
  const clickable = nodes.filter((node) => node.clickable).length;
  const withText = nodes.filter((node) => node.text).length;
  return {
    snapshotId: snapshot?.snapshotId ?? "-",
    nodeCount: nodes.length,
    clickable,
    withText,
    window: snapshot?.windowSizePx ? `${snapshot.windowSizePx.width}×${snapshot.windowSizePx.height}` : "-",
  };
}

async function load() {
  statusEl.textContent = "正在读取快照…";
  try {
    const snapshot = await $u.snapshot.get();
    if (!snapshot) {
      statusEl.textContent = "当前没有快照，请先在工具轨点击「抓取布局快照」。";
      render([]);
      return;
    }
    lastSummary = summarize(snapshot);
    statusEl.textContent = "快照已就绪。";
    render([
      ["快照 ID", lastSummary.snapshotId],
      ["节点总数", lastSummary.nodeCount],
      ["可点击节点", lastSummary.clickable],
      ["含文本节点", lastSummary.withText],
      ["窗口尺寸", lastSummary.window],
    ]);
  } catch (error) {
    statusEl.textContent = `读取失败：${error.message}`;
  }
}

document.getElementById("refresh").addEventListener("click", load);

document.getElementById("copy").addEventListener("click", async () => {
  if (!lastSummary) return;
  await $u.host.copyText(JSON.stringify(lastSummary, null, 2));
  await $u.ui.toast("统计已复制");
});

exportButton.addEventListener("click", async () => {
  if (!lastSummary) return;
  try {
    await $u.host.saveFile(`${lastSummary.snapshotId}-overview.json`, JSON.stringify(lastSummary, null, 2));
    await $u.ui.toast("已导出统计文件");
  } catch (error) {
    // 浏览器宿主没有保存能力，降级为复制
    await $u.host.copyText(JSON.stringify(lastSummary, null, 2));
    await $u.ui.toast("当前宿主不支持保存文件，已改为复制", "danger");
  }
});

(async () => {
  try {
    const context = await $u.host.getContext();
    statusEl.textContent = `宿主：${context.host} · 设备：${context.deviceId}`;
    // 能力查询而不是环境嗅探：壳里才显示导出按钮
    exportButton.hidden = !(await $u.host.can("saveFile"));
    await load();
  } catch (error) {
    statusEl.textContent = `无法连接宿主桥：${error.message}`;
  }
})();
