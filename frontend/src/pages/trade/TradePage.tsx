import { useCallback, useEffect, useRef } from "react";
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

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
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
        className="w-2 cursor-col-resize hover:bg-brand-primary/10 bg-surface-canvas transition-colors flex-shrink-0"
        onMouseDown={handleMouseDown}
      />

      <div
        className="h-full min-h-0 overflow-hidden flex-shrink-0"
        style={{ width: `${inspectorWidth}px` }}
      >
        <AccountInspectorPanel />
      </div>
    </section>
  );
}
