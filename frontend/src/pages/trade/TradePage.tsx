import { useCallback, useEffect, useRef, useState } from "react";
import { AccountSessionSidebar } from "@/features/trade/AccountSessionSidebar";
import { SessionHeader } from "@/features/trade/SessionHeader";
import { LLMLinearTimeline } from "@/features/trade/LLMLinearTimeline";
import { ChatInputBox } from "@/features/trade/ChatInputBox";
import { AccountInspectorPanel } from "@/features/trade/AccountInspectorPanel";
import { useUIStore } from "@/stores/uiStore";

export function TradePage() {
  const leftCollapsed = useUIStore((s) => s.leftCollapsed);
  const inspectorWidth = useUIStore((s) => s.inspectorWidth);
  const setInspectorWidth = useUIStore((s) => s.setInspectorWidth);
  const dragging = useRef(false);
  const [draggingInspector, setDraggingInspector] = useState(false);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    setDraggingInspector(true);
  }, []);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const next = Math.min(
        Math.max(window.innerWidth - e.clientX, 420),
        Math.round(window.innerWidth * 0.7)
      );
      setInspectorWidth(next);
    };
    const onMouseUp = () => {
      dragging.current = false;
      setDraggingInspector(false);
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [setInspectorWidth]);

  return (
    <section className={`flex h-full min-h-0 overflow-hidden ${leftCollapsed ? "left-collapsed" : ""}`}>
      <AccountSessionSidebar />

      <div className="flex-1 min-w-[520px] flex flex-col min-h-0">
        <SessionHeader />
        <LLMLinearTimeline />
        <ChatInputBox />
      </div>

      <div
        className={`group relative w-2 cursor-col-resize bg-surface-canvas transition-colors hover:bg-brand-primary/10 flex-shrink-0 ${
          draggingInspector ? "bg-brand-primary/10" : ""
        }`}
        onMouseDown={handleMouseDown}
        title="Resize account inspector"
      >
        <span
          className={`absolute left-1/2 top-1/2 h-14 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full transition-colors ${
            draggingInspector ? "bg-brand-primary" : "bg-hairline group-hover:bg-brand-primary"
          }`}
        />
      </div>

      <div
        className="h-full min-h-0 overflow-hidden flex-shrink-0"
        style={{ width: `${inspectorWidth}px` }}
      >
        <AccountInspectorPanel />
      </div>
    </section>
  );
}
