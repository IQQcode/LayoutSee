import { Component } from "react";
import { HostBridge } from "./HostBridge.js";

export class GlobalErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 32 }}>
          <section style={{ maxWidth: 460, display: "grid", gap: 8, justifyItems: "center", textAlign: "center" }}>
            <h1 style={{ margin: 0, fontSize: 18 }}>界面发生错误</h1>
            <p style={{ margin: 0, color: "var(--ls-color-text-secondary)", lineHeight: 1.6 }}>
              当前页面无法继续渲染，设备连接与已有快照不受影响。请重新加载页面，或复制诊断信息反馈问题。
            </p>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button className="button" onClick={() => window.location.reload()}>重新加载</button>
              <button
                className="button primary"
                onClick={async () => {
                  // 壳走 IPC 汇总，浏览器由 HostBridge 汇总后写剪贴板
                  await HostBridge.copySanitizedDiagnostics().catch(() => {});
                }}
              >
                复制诊断
              </button>
            </div>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
