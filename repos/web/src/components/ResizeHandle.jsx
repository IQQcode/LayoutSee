import { useEffect, useRef, useState } from "react";
import { ArrowsLeftRight } from "@phosphor-icons/react";

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, Math.round(value)));
}

export function ResizeHandle({ label, value, min, max, onChange, onReset, orientation = "vertical", className = "" }) {
  const dragStart = useRef(null);
  const dragCleanup = useRef(() => {});
  const [active, setActive] = useState(false);

  useEffect(() => () => {
    dragCleanup.current();
    document.body.classList.remove("is-resizing");
  }, []);

  const step = 12;
  const shiftStep = 32;
  const horizontal = orientation !== "horizontal";

  return (
    <button
      type="button"
      className={`resize-handle ${orientation === "horizontal" ? "vertical" : ""} ${active ? "active" : ""} ${className}`}
      role="separator"
      aria-label={label}
      aria-orientation={horizontal ? "vertical" : "horizontal"}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      aria-valuetext={`${Math.round(value)} 像素`}
      title={`${label}；双击恢复默认宽度`}
      onDoubleClick={onReset}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        const handle = event.currentTarget;
        const pointerId = event.pointerId;
        dragStart.current = { x: event.clientX, y: event.clientY, value };
        setActive(true);
        document.body.classList.add("is-resizing");
        handle.setPointerCapture?.(pointerId);
        const move = (moveEvent) => {
          if (!dragStart.current || moveEvent.pointerId !== pointerId) return;
          const delta = horizontal ? moveEvent.clientX - dragStart.current.x : moveEvent.clientY - dragStart.current.y;
          onChange(clamp(dragStart.current.value + delta, min, max));
        };
        const finish = () => {
          window.removeEventListener("pointermove", move, true);
          window.removeEventListener("pointerup", finish, true);
          window.removeEventListener("pointercancel", finish, true);
          if (handle.hasPointerCapture?.(pointerId)) handle.releasePointerCapture(pointerId);
          dragStart.current = null;
          setActive(false);
          document.body.classList.remove("is-resizing");
        };
        window.addEventListener("pointermove", move, true);
        window.addEventListener("pointerup", finish, true);
        window.addEventListener("pointercancel", finish, true);
        dragCleanup.current = finish;
      }}
      onKeyDown={(event) => {
        const amount = event.shiftKey ? shiftStep : step;
        if (event.key === "ArrowLeft") onChange(clamp(value - amount, min, max));
        else if (event.key === "ArrowRight") onChange(clamp(value + amount, min, max));
        else if (event.key === "ArrowUp") onChange(clamp(value - amount, min, max));
        else if (event.key === "ArrowDown") onChange(clamp(value + amount, min, max));
        else if (event.key === "Home") onChange(min);
        else if (event.key === "End") onChange(max);
        else return;
        event.preventDefault();
      }}
    >
      <ArrowsLeftRight size={13} aria-hidden="true" />
    </button>
  );
}
