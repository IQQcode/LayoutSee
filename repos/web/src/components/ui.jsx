import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { CheckCircle, WarningCircle, XCircle, X } from "@phosphor-icons/react";
import { MorphGlyph } from "./MorphIcons.jsx";

// icon 既可是图标组件（Phosphor 等），也可是 Lucide 图标数据（数组，交给 MorphGlyph）。
// 传数据却按组件渲染会直接抛 React #130，这里统一兜住。
export function Button({ children, icon, variant = "", compact = false, loading = false, className = "", ...props }) {
  const isData = Array.isArray(icon);
  const Icon = isData ? null : icon;
  return (
    <button className={`button ${variant} ${compact ? "compact" : ""} ${loading ? "loading" : ""} ${className}`} {...props}>
      {loading ? (
        <span className="spinner" aria-hidden="true" />
      ) : isData ? (
        <MorphGlyph icon={icon} size={15} strokeWidth={1.9} />
      ) : Icon ? (
        <Icon size={15} weight="regular" aria-hidden="true" />
      ) : null}
      {children ? <span>{children}</span> : null}
    </button>
  );
}

export function IconButton({ icon: Icon, label, active = false, danger = false, className = "", tooltip, children, ...props }) {
  return (
    <button
      className={`icon-button ${active ? "is-active" : ""} ${danger ? "danger-active" : ""} ${className}`}
      aria-label={label}
      title={tooltip || label}
      {...props}
    >
      {Icon ? <Icon size={18} weight="regular" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function StatusPill({ tone = "neutral", dot = false, children }) {
  return (
    <span className={`status-pill ${tone}`}>
      {dot ? <span className="status-dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function Banner({ tone = "info", icon: Icon, children }) {
  return (
    <div className={`banner ${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {Icon ? <Icon size={17} aria-hidden="true" /> : null}
      <div className="banner-body">{children}</div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, description, children }) {
  return (
    <div className="empty-state">
      <div className="empty-icon" aria-hidden="true">{Icon ? <Icon size={26} /> : null}</div>
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {children}
    </div>
  );
}

export function Spinner({ label = "加载中" }) {
  return <span className="spinner" role="status" aria-label={label} />;
}

export function Dialog({ title, open, onClose, children, footer }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="dialog-mask" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="dialog-head">
          <h2>{title}</h2>
          <IconButton icon={X} label="关闭" onClick={onClose} />
        </div>
        <div className="dialog-body">{children}</div>
        {footer ? <div className="dialog-foot">{footer}</div> : null}
      </div>
    </div>
  );
}

export function CopyButton({ value, label = "复制", onCopied }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef(0);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const area = document.createElement("textarea");
      area.value = value;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setCopied(true);
    onCopied?.();
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1600);
  };
  return (
    <button type="button" className="copy-inline" aria-label={`${label}：${value}`} title={label} onClick={copy}>
      {copied ? <CheckCircle size={14} weight="fill" aria-hidden="true" /> : null}
      {copied ? "已复制" : label}
    </button>
  );
}

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const timer = useRef(0);
  const show = useCallback((message, tone = "success") => {
    setToast({ message, tone });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), 2400);
  }, []);
  const Icon = toast?.tone === "danger" ? XCircle : toast?.tone === "warning" ? WarningCircle : CheckCircle;
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast ? (
        <div className="toast" role="status">
          <Icon size={16} aria-hidden="true" />
          {toast.message}
        </div>
      ) : null}
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
