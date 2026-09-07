import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowClockwise, ArrowsCounterClockwise, CaretDown, CaretRight, Code, DownloadSimple, MagnifyingGlass, Copy } from "@phosphor-icons/react";
import { api } from "../../../api/client.js";
import { HostBridge } from "../../../app/HostBridge.js";
import { LogTags, uiLog, uiLogApi } from "../../../api/logger.js";
import { Banner, Button, CopyButton, EmptyState, Spinner } from "../../../components/ui.jsx";
import { ResizeHandle, clamp } from "../../../components/ResizeHandle.jsx";

function serializeNode(node, nodes) {
  const children = nodes.filter((item) => item.parentKey === node.nodeKey);
  const attrs = Object.entries(node.raw || {})
    .map(([key, value]) => ` ${key}="${String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;")}"`)
    .join("");
  if (children.length === 0) return `<node${attrs}/>`;
  return `<node${attrs}>${children.map((child) => serializeNode(child, nodes)).join("")}</node>`;
}

function precheckXpath(expression) {
  if (!expression.trim()) return "请输入 XPath 表达式";
  try {
    const evaluator = new XPathEvaluator();
    evaluator.createExpression(expression, null);
    return null;
  } catch (error) {
    return `XPath 语法错误：${error.message || error}`;
  }
}

// XPath 生成维度：值对应 Core /selectors 候选的 kind 字段
const XPATH_MODES = [
  { id: "custom", label: "自定义" },
  { id: "id", label: "id" },
  { id: "text", label: "text" },
  { id: "class", label: "class" },
];
// 命中过多时不铺满序号按钮，改成跳转输入框
const MATCH_CHIP_LIMIT = 200;

// 命中序号越界收敛：空集合返回 -1，其余夹在 [0, length-1]。抽成纯函数以便单测
function boundedMatchIndex(index, length) {
  if (length <= 0) return -1;
  return Math.min(Math.max(index, 0), length - 1);
}

export function ElementTab({ device, deviceId, snapshotMeta, snapshotData, capturing, onCapture, onSelectNode, selectedNode, setHighlights, onToast, onViewReset, snapshotView }) {
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState(() => new Set());
  const [xpath, setXpath] = useState("");
  const [xpathMode, setXpathMode] = useState("custom");
  const [xpathError, setXpathError] = useState(null);
  const [xpathResult, setXpathResult] = useState(null);
  const [matchIndex, setMatchIndex] = useState(0);
  const [querying, setQuerying] = useState(false);
  const [selectors, setSelectors] = useState(null);
  const [selectorsFor, setSelectorsFor] = useState(null);
  const [propertyWidth, setPropertyWidth] = useState(230);
  const [exporting, setExporting] = useState(false);
  const inspectorRef = useRef(null);
  const treeRef = useRef(null);
  const nodeIndexRef = useRef(new Map());

  const nodes = snapshotData?.nodes ?? [];
  const byKey = useMemo(() => {
    const map = new Map();
    for (const node of nodes) map.set(node.nodeKey, node);
    return map;
  }, [nodes]);

  useEffect(() => {
    if (snapshotData) uiLog(LogTags.element, "快照已加载", "info", `${snapshotData.snapshotId} · ${snapshotData.nodes.length} 节点`);
  }, [snapshotData]);

  // 快照加载后默认展开整棵层级树，用户可直接浏览（对齐 UIAutoDev 的平铺体验）
  useEffect(() => {
    if (!snapshotData) {
      setExpanded(new Set());
      return;
    }
    setExpanded(new Set(snapshotData.nodes.map((node) => node.nodeKey)));
  }, [snapshotData]);

  useEffect(() => {
    const inspector = inspectorRef.current;
    if (!inspector) return undefined;
    const update = () => {
      const width = Math.round(inspector.getBoundingClientRect().width);
      setPropertyWidth((current) => clamp(current, 150, Math.max(150, width - 220)));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(inspector);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (selectedNode && nodes.length) {
      const chain = [];
      let current = byKey.get(selectedNode);
      while (current) {
        chain.unshift(current.nodeKey);
        current = current.parentKey ? byKey.get(current.parentKey) : null;
      }
      setExpanded((current) => {
        const next = new Set(current);
        for (const key of chain) next.add(key);
        return next;
      });
      treeRef.current?.querySelector(`[data-node-key="${selectedNode}"]`)?.scrollIntoView({ block: "nearest" });
    }
  }, [selectedNode, nodes.length, byKey]);

  useEffect(() => {
    if (!snapshotData || !selectedNode) {
      setSelectors(null);
      setSelectorsFor(null);
      return;
    }
    let active = true;
    setSelectorsFor(selectedNode);
    uiLogApi(LogTags.element, `生成选择器 ${selectedNode}`, () => api.selectors(snapshotData.snapshotId, selectedNode))
      .then((payload) => active && setSelectors(payload.selectors ?? []))
      .catch(() => active && setSelectors([]));
    return () => {
      active = false;
    };
  }, [snapshotData, selectedNode]);

  // 选定生成维度后，选中节点一变就按该维度回填表达式（对齐 uiautodev 的 XPath by）
  useEffect(() => {
    if (xpathMode === "custom" || !selectors?.length) return;
    const candidate = selectors.find((item) => item.kind === xpathMode);
    if (candidate) {
      setXpath(candidate.expression);
      setXpathError(null);
    }
  }, [selectors, xpathMode]);

  const gotoMatch = useCallback((index) => {
    const keys = xpathResult?.nodeKeys ?? [];
    const bounded = boundedMatchIndex(index, keys.length);
    if (bounded < 0) return;
    setMatchIndex(bounded);
    onSelectNode(keys[bounded]);
  }, [xpathResult, onSelectNode]);

  const visibleNodes = useMemo(() => {
    if (!filter.trim()) return nodes;
    const query = filter.trim().toLowerCase();
    const matched = new Set();
    for (const node of nodes) {
      const haystack = `${node.className} ${node.resourceId ?? ""} ${node.text ?? ""} ${node.contentDescription ?? ""}`.toLowerCase();
      if (haystack.includes(query)) matched.add(node.nodeKey);
    }
    const keep = new Set();
    for (const node of nodes) {
      if (!matched.has(node.nodeKey)) continue;
      keep.add(node.nodeKey);
      let parent = node.parentKey;
      while (parent) {
        keep.add(parent);
        parent = byKey.get(parent)?.parentKey;
      }
    }
    return nodes.filter((node) => keep.has(node.nodeKey));
  }, [nodes, filter, byKey]);

  const selected = selectedNode ? byKey.get(selectedNode) : null;
  const rootNodes = visibleNodes.filter((node) => !node.parentKey || !byKey.get(node.parentKey) || !visibleNodes.includes(byKey.get(node.parentKey)));
  const childrenOf = useCallback((key) => visibleNodes.filter((node) => node.parentKey === key), [visibleNodes]);

  const runXpath = async () => {
    const problem = precheckXpath(xpath);
    if (problem) {
      setXpathError(problem);
      return;
    }
    setXpathError(null);
    if (!snapshotData) {
      onToast?.("请先抓取布局快照", "warning");
      return;
    }
    setQuerying(true);
    try {
      const result = await uiLogApi(LogTags.element, `XPath 查询「${xpath.slice(0, 80)}」`, () => api.xpath(snapshotData.snapshotId, xpath));
      setXpathResult(result);
      setMatchIndex(0);
      if (result.matchCount === 0) {
        uiLog(LogTags.element, "XPath 零命中，已保留当前选中节点", "warning");
        onToast?.("查询完成：0 个命中，已保留当前选中节点");
      } else {
        const next = {};
        for (const key of result.nodeKeys) next[key] = "xpath";
        setHighlights(next);
        onSelectNode(result.nodeKeys[0]);
        uiLog(LogTags.element, "XPath 命中", "info", `${result.matchCount} 个节点`);
        onToast?.(`查询完成：命中 ${result.matchCount} 个节点`);
      }
    } catch (error) {
      setXpathError(error.message);
    } finally {
      setQuerying(false);
    }
  };

  const renderTree = (keys) => keys.map((key) => {
    const node = byKey.get(key);
    if (!node) return null;
    const children = childrenOf(key);
    const isOpen = expanded.has(key);
    const label = node.resourceId || node.text || node.contentDescription || node.className;
    return (
      <div key={key} role="treeitem" aria-expanded={children.length ? isOpen : undefined} data-node-key={key}>
        <button
          type="button"
          className={`tree-node ${selectedNode === key ? "selected" : ""}`}
          style={{ paddingLeft: 8 + node.depth * 14 }}
          title={label}
          onClick={() => onSelectNode(key)}
        >
          <span
            className="tree-chevron"
            role="button"
            tabIndex={0}
            aria-label={isOpen ? "折叠" : "展开"}
            onClick={(event) => {
              event.stopPropagation();
              setExpanded((current) => {
                const next = new Set(current);
                if (next.has(key)) next.delete(key);
                else next.add(key);
                return next;
              });
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.stopPropagation();
                event.preventDefault();
                setExpanded((current) => {
                  const next = new Set(current);
                  if (next.has(key)) next.delete(key);
                  else next.add(key);
                  return next;
                });
              }
            }}
          >
            {children.length ? (isOpen ? <CaretDown size={11} /> : <CaretRight size={11} />) : null}
          </span>
          <code className="xml-line">
            <span className="tok-punct">&lt;</span>
            <span className="tok-tag">{node.className}</span>
            {node.resourceId ? (
              <><span className="tok-attr"> resource-id</span><span className="tok-punct">=</span><span className="tok-value">"{node.resourceId}"</span></>
            ) : null}
            {node.text ? (
              <><span className="tok-attr"> text</span><span className="tok-punct">=</span><span className="tok-value">"{node.text.length > 28 ? `${node.text.slice(0, 28)}…` : node.text}"</span></>
            ) : null}
            {!node.resourceId && !node.text && node.contentDescription ? (
              <><span className="tok-attr"> content-desc</span><span className="tok-punct">=</span><span className="tok-value">"{node.contentDescription.length > 24 ? `${node.contentDescription.slice(0, 24)}…` : node.contentDescription}"</span></>
            ) : null}
            {node.clickable ? <span className="tok-flag"> clickable</span> : null}
            <span className="tok-punct">{children.length ? ">" : "/>"}</span>
          </code>
        </button>
        {isOpen && children.length ? renderTree(children.map((child) => child.nodeKey)) : null}
      </div>
    );
  });

  const copyXml = () => {
    if (!selected) return;
    const xml = serializeNode(selected, nodes);
    navigator.clipboard.writeText(xml).then(() => onToast?.("节点 XML 已复制")).catch(() => {});
  };

  const buildLayoutXml = useCallback(() => {
    if (!snapshotData) return "";
    const roots = nodes.filter((node) => !node.parentKey || !byKey.get(node.parentKey));
    const inner = roots.map((root) => serializeNode(root, nodes)).join("");
    return `<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>\n<hierarchy rotation="0">${inner}</hierarchy>`;
  }, [snapshotData, nodes, byKey]);

  const exportLayout = async () => {
    if (!snapshotData) {
      onToast?.("请先抓取布局快照", "warning");
      return;
    }
    setExporting(true);
    const name = `${deviceId}-layout-${snapshotData.snapshotId}.xml`;
    try {
      const xml = buildLayoutXml();
      const result = await HostBridge.exportLayout(name, xml);
      if (result?.saved) {
        uiLog(LogTags.element, "布局已导出", "info", result.path);
        onToast?.(`布局已导出到 ${result.path}`);
      } else if (result?.fallback) {
        // 无壳环境（浏览器）兜底：直接下载
        const blob = new Blob([xml], { type: "text/xml" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = name;
        anchor.click();
        URL.revokeObjectURL(url);
        uiLog(LogTags.element, "布局已下载", "info", name);
        onToast?.("布局 XML 已下载");
      }
    } catch (error) {
      uiLog(LogTags.element, "布局导出失败", "error", error.message);
      onToast?.(error.message, "danger");
    } finally {
      setExporting(false);
    }
  };

  // 属性顺序：resource-id 置顶（无值不占行），其后 nodeKey/className/bounds 与其余原始属性
  const properties = (() => {
    if (!selected) return [];
    const rows = [];
    if (selected.raw?.["resource-id"]) rows.push(["resource-id", selected.raw["resource-id"]]);
    rows.push(["nodeKey", selected.nodeKey]);
    rows.push(["className", selected.className]);
    rows.push(["bounds", `[${selected.boundsPx.left},${selected.boundsPx.top}][${selected.boundsPx.right},${selected.boundsPx.bottom}]`]);
    for (const [key, value] of Object.entries(selected.raw || {})) {
      if (key === "resource-id" || key === "bounds") continue;
      rows.push([key, value]);
    }
    return rows;
  })();

  return (
    <div className="element-panel" style={{ display: "flex", flexDirection: "column", height: "100%", padding: 14 }}>
      <div className="xpath-row">
        <select
          className="xpath-mode"
          value={xpathMode}
          aria-label="XPath 生成维度"
          onChange={(event) => setXpathMode(event.target.value)}
        >
          {XPATH_MODES.map((mode) => (
            <option key={mode.id} value={mode.id}>XPath by {mode.label}</option>
          ))}
        </select>
        <div className="xpath-input">
          <Code size={15} aria-hidden="true" />
          <input
            value={xpath}
            onChange={(event) => { setXpath(event.target.value); setXpathError(null); setXpathMode("custom"); }}
            onKeyDown={(event) => { if (event.key === "Enter") runXpath(); if (event.key === "Escape") { setXpath(""); setXpathResult(null); } }}
            placeholder="//*[@resource-id='com.example:id/btn']"
            aria-label="XPath 表达式"
          />
          <button className="copy-inline" aria-label="清空 XPath" onClick={() => { setXpath(""); setXpathResult(null); }}>×</button>
        </div>
        <Button variant="primary" icon={MagnifyingGlass} loading={querying} onClick={runXpath}>查询</Button>
      </div>
      {xpathError ? <p className="xpath-error" role="alert">{xpathError}</p> : null}
      {xpathResult?.matchCount > 1 ? (
        <div className="match-index-row" role="group" aria-label="XPath 命中节点切换">
          <span>命中 {xpathResult.matchCount} 个</span>
          {xpathResult.matchCount <= MATCH_CHIP_LIMIT ? (
            xpathResult.nodeKeys.map((key, index) => (
              <button
                key={key}
                type="button"
                className={`match-chip ${index === matchIndex ? "active" : ""}`}
                aria-current={index === matchIndex}
                aria-label={`定位第 ${index + 1} 个命中节点`}
                onClick={() => gotoMatch(index)}
              >
                {index + 1}
              </button>
            ))
          ) : (
            <input
              className="match-jump"
              type="number"
              min={1}
              max={xpathResult.matchCount}
              value={matchIndex + 1}
              aria-label="跳转到第几个命中节点"
              onChange={(event) => gotoMatch(Number(event.target.value) - 1)}
            />
          )}
        </div>
      ) : null}

      <div className="element-toolbar">
        <div style={{ display: "flex", gap: 6 }}>
          <Button compact icon={ArrowClockwise} loading={capturing} onClick={onCapture}>抓取 UI 快照</Button>
          <Button compact icon={ArrowsCounterClockwise} onClick={() => {
              setFilter("");
              setXpath("");
              setXpathResult(null);
              setXpathMode("custom");
              setMatchIndex(0);
              setHighlights({});
              onViewReset?.();
              onToast?.(snapshotView ? "已返回实时投屏" : undefined);
            }}
          >
            重置
          </Button>
          <Button compact icon={DownloadSimple} loading={exporting} disabled={!snapshotData} onClick={exportLayout}>导出</Button>
        </div>
        <div className="selected-meta">
          {xpathResult ? <span>命中 <b>{xpathResult.matchCount}</b></span> : null}
          <span>节点 <b>{nodes.length}</b></span>
          {snapshotMeta?.synchronization === "context_changed" ? <span className="status-pill warning">不同步</span> : null}
        </div>
      </div>

      {snapshotData ? (
        <div className="inspector-grid" ref={inspectorRef} style={{ flex: 1, minHeight: 0, gridTemplateColumns: `${propertyWidth}px 8px minmax(0, 1fr)` }}>
          <section className="property-pane" aria-label="节点属性">
            <div className="inspector-head">
              <strong>属性</strong>
              <span>{properties.length} 项</span>
            </div>
            {selected ? (
              <>
                <div className="property-list">
                  {properties.map(([key, value]) => (
                    <div className="property-row" key={key}>
                      <span>{key}</span><code>{String(value ?? "—")}</code><CopyButton value={String(value ?? "")} />
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 6, padding: "8px 10px", borderTop: "1px solid var(--ls-color-border-default)", flexWrap: "wrap" }}>
                  <Button compact onClick={copyXml}>复制 XML</Button>
                  <Button compact onClick={() => navigator.clipboard.writeText(JSON.stringify(selected.raw, null, 2)).then(() => onToast?.("属性 JSON 已复制")).catch(() => {})}>复制属性 JSON</Button>
                </div>
              </>
            ) : (
              <div className="tree-empty">在层级树中选择一个节点，或在审查模式下点击画面。</div>
            )}
          </section>
          <ResizeHandle
            label="调整属性面板宽度"
            value={propertyWidth}
            min={150}
            max={Math.max(150, (inspectorRef.current?.getBoundingClientRect().width ?? 600) - 220)}
            onChange={setPropertyWidth}
            onReset={() => setPropertyWidth(230)}
          />
          <section className="tree-pane" aria-label="UI 层级树">
            <div className="inspector-head">
              <strong>UI 层级</strong>
              <span>{snapshotData.nodes.length} 个节点</span>
            </div>
            <div className="tree-filter">
              <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="按文本、resource-id 或类名过滤" aria-label="过滤层级树" />
            </div>
            <div className="tree-scroll" ref={treeRef} role="tree" aria-label="UI 层级树">
              {visibleNodes.length ? renderTree(rootNodes.map((node) => node.nodeKey)) : <div className="tree-empty">没有匹配的节点</div>}
            </div>
          </section>
        </div>
      ) : (
        <EmptyState icon={Code} title="还没有布局快照" description="点击「立即抓取」后，左侧将进入布局查看模式：画面叠加元素边框，点选即可查看属性与层级。">
          <Button variant="primary" icon={ArrowClockwise} loading={capturing} onClick={onCapture}>立即抓取</Button>
        </EmptyState>)}

      {selectors && selectorsFor === selectedNode ? (
        <section className="content-card" style={{ marginTop: 12, marginBottom: 0 }}>
          <div className="card-heading">
            <div>
              <h3>候选选择器</h3>
              <p>每个候选已在当前快照上重新执行；仅命中 1 次的候选标记为稳定</p>
            </div>
            <span className="count-pill">{selectors.length} 个</span>
          </div>
          <div className="selector-list">
            {selectors.map((selector) => (
              <div className="selector-item" key={selector.expression}>
                <code>{selector.expression}</code>
                <span className={`match-pill status-pill ${selector.stable ? "success" : "warning"}`}>{selector.matchCount} 命中</span>
                {!selector.stable ? <span className="unstable-tag">不稳定</span> : null}
                <CopyButton value={selector.expression} label="复制" />
              </div>
            ))}
            {selectors.length === 0 ? <div className="tree-empty">未生成可用候选</div> : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
