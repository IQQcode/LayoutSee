import { useCallback, useState } from "react";
import { ArrowClockwise, Copy, Sparkle, Stethoscope } from "@phosphor-icons/react";
import { api } from "../../../api/client.js";
import { LogTags, uiLog, uiLogApi } from "../../../api/logger.js";
import { Banner, Button, EmptyState, StatusPill } from "../../../components/ui.jsx";

const SEVERITY_TEXT = { error: "错误", warning: "警告", info: "提示" };
const TYPE_TEXT = {
  overlap: "重叠", occlusion: "遮挡", out_of_bounds: "越界",
  small_touch_target: "触控热区过小", text_truncation: "文本截断", invisible_interactive: "隐形可交互",
};

export function IntelligenceTab({ deviceId, snapshotMeta, snapshotData, onCapture, capturing, onShowFinding, onSelectNode, onToast }) {
  const [summary, setSummary] = useState(null);
  const [summarizing, setSummarizing] = useState(false);
  const [summaryError, setSummaryError] = useState(null);
  const [diagnostics, setDiagnostics] = useState(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnosticsError, setDiagnosticsError] = useState(null);

  const runSummary = useCallback(async () => {
    setSummarizing(true);
    setSummaryError(null);
    try {
      const result = await uiLogApi(LogTags.intelligence, `生成语义摘要 ${snapshotData.snapshotId}`, () => api.summary(snapshotData.snapshotId));
      setSummary(result);
      uiLog(LogTags.intelligence, "摘要完成", "info", `约 ${result.estimatedTokens ?? "?"} tokens · partial=${result.partial ?? false}`);
    } catch (error) {
      setSummaryError(error);
    } finally {
      setSummarizing(false);
    }
  }, [snapshotData]);

  const runDiagnostics = useCallback(async () => {
    setDiagnosing(true);
    setDiagnosticsError(null);
    try {
      const result = await uiLogApi(LogTags.intelligence, `生成布局诊断 ${snapshotData.snapshotId}`, () => api.layoutDiagnostics(snapshotData.snapshotId));
      setDiagnostics(result);
      uiLog(LogTags.intelligence, "诊断完成", "info", `${result.findings?.length ?? 0} 条发现`);
    } catch (error) {
      setDiagnosticsError(error);
    } finally {
      setDiagnosing(false);
    }
  }, [snapshotData]);

  if (!snapshotData) {
    return (
      <div className="panel-scroll">
        <div className="panel-title">
          <div>
            <h2>布局智能</h2>
            <p>从当前快照生成语义摘要与六类布局诊断</p>
          </div>
        </div>
        <EmptyState icon={Sparkle} title="还没有布局快照" description="语义摘要与布局诊断都基于当前快照，先抓取一次再开始分析。">
          <Button variant="primary" icon={ArrowClockwise} loading={capturing} onClick={onCapture}>立即抓取</Button>
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="panel-scroll">
      <div className="panel-title">
        <div>
          <h2>布局智能</h2>
          <p>快照 {snapshotData.snapshotId.slice(0, 16)} · {snapshotData.nodes.length} 个节点</p>
        </div>
      </div>

      <section className="content-card">
        <div className="card-heading">
          <div>
            <h3>语义摘要</h3>
            <p>确定性生成，元素携带短 ref 供 Agent 引用；重复生成结果一致</p>
          </div>
          <Button compact icon={Sparkle} loading={summarizing} onClick={runSummary}>生成摘要</Button>
        </div>
        {summaryError ? <Banner tone="danger"><b>摘要生成失败</b>：{summaryError.message}</Banner> : null}
        {summary ? (
          <>
            <div className="metric-row" style={{ marginBottom: 10 }}>
              <div className="metric"><b>{summary.estimatedTokens}</b><span>估算 Token</span></div>
              <div className="metric"><b>{summary.coverage.includedInteractive}/{summary.coverage.totalInteractive}</b><span>可交互元素</span></div>
              <div className="metric"><b>{summary.partial ? "部分" : "完整"}</b><span>覆盖状态</span></div>
            </div>
            {summary.partial ? (
              <Banner tone="warning" style={{ marginBottom: 10 }}>
                <b>输出已被裁剪</b>：省略 {summary.coverage.omittedInteractive} 个可交互元素与 {summary.coverage.omittedSemanticText} 个文本节点，请调用 find_element 继续查询。
              </Banner>
            ) : null}
            <pre className="summary-output">{summary.text}</pre>
            <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end" }}>
              <Button compact icon={Copy} onClick={() => navigator.clipboard.writeText(summary.text).then(() => onToast?.("摘要已复制")).catch(() => {})}>复制摘要</Button>
            </div>
          </>
        ) : null}
      </section>

      <section className="content-card">
        <div className="card-heading">
          <div>
            <h3>布局诊断</h3>
            <p>覆盖遮挡、重叠、越界、触控热区过小、文本截断与隐形可交互六类问题</p>
          </div>
          <Button compact icon={Stethoscope} loading={diagnosing} onClick={runDiagnostics}>开始诊断</Button>
        </div>
        {diagnosticsError ? <Banner tone="danger"><b>诊断失败</b>：{diagnosticsError.message}</Banner> : null}
        {diagnostics ? (
          <>
            <div className="metric-row" style={{ marginBottom: 10 }}>
              <div className="metric"><b>{diagnostics.findings.length}</b><span>发现问题</span></div>
              <div className="metric"><b>{diagnostics.nodesChecked}</b><span>已检查节点</span></div>
              <div className="metric"><b>{diagnostics.elapsedMs}ms</b><span>耗时</span></div>
            </div>
            {diagnostics.findings.length === 0 ? (
              <Banner tone="info">已检查 {diagnostics.rulesChecked.length} 类规则与 {diagnostics.nodesChecked} 个节点，未发现异常。</Banner>
            ) : (
              <div className="finding-list">
                {diagnostics.findings.map((finding) => (
                  <article
                    key={finding.findingId}
                    className={`finding-item ${finding.severity}`}
                    tabIndex={0}
                    role="button"
                    onClick={() => { onShowFinding(finding); onSelectNode(finding.nodeKeys[0]); }}
                    onKeyDown={(event) => { if (event.key === "Enter") { onShowFinding(finding); onSelectNode(finding.nodeKeys[0]); } }}
                  >
                    <div className="finding-head">
                      <StatusPill tone={finding.severity === "error" ? "danger" : finding.severity === "warning" ? "warning" : "info"} dot>
                        {SEVERITY_TEXT[finding.severity]}
                      </StatusPill>
                      <b>{TYPE_TEXT[finding.type] ?? finding.type}</b>
                      <span style={{ marginLeft: "auto", color: "var(--ls-color-text-tertiary)", fontSize: 11 }}>置信度 {finding.confidence}</span>
                    </div>
                    <p className="finding-evidence">{finding.evidence}</p>
                    <p className="finding-suggestion">建议：{finding.suggestion}</p>
                  </article>
                ))}
              </div>
            )}
          </>
        ) : null}
      </section>
    </div>
  );
}
