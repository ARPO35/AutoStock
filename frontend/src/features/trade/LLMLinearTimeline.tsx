import { useEffect, useMemo, useRef, useState } from "react";
import { useTradeStore } from "@/stores/tradeStore";
import { EmptyState, LoadingDots, Spinner } from "@/components/ui/Shared";
import { MessageBubble } from "@/features/trade/MessageBubble";

export function LLMLinearTimeline() {
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const loadTimeline = useTradeStore((s) => s.loadTimeline);
  const busy = useTradeStore((s) => s.busy);
  const loadingTimeline = useTradeStore((s) => s.loadingTimeline);

  const timelineSource = useTradeStore((s) => s.timelineSource);
  const optimisticUserMessage = useTradeStore((s) => s.optimisticUserMessage);
  const lastModel = useTradeStore((s) => s.lastModel);
  const lastRunLatencyMs = useTradeStore((s) => s.lastRunLatencyMs);
  const streamedRounds = useTradeStore((s) => s.streamedRounds);
  const currentReasoning = useTradeStore((s) => s.currentReasoning);
  const currentContent = useTradeStore((s) => s.currentContent);
  const currentToolCalls = useTradeStore((s) => s.currentToolCalls);
  const focusedToolCallId = useTradeStore((s) => s.focusedToolCallId);
  const focusToolCall = useTradeStore((s) => s.focusToolCall);

  const timeline = useMemo(
    () => useTradeStore.getState().getTimeline(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [timelineSource, optimisticUserMessage, lastModel, lastRunLatencyMs,
     streamedRounds, currentReasoning, currentContent, currentToolCalls]
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastScrollTopRef = useRef(0);
  const manuallyUnlockedRef = useRef(false);
  const scrollFrameRef = useRef<number | null>(null);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);

  const RELOCK_THRESHOLD_PX = 48;

  const getDistanceToBottom = (el: HTMLDivElement) => (
    el.scrollHeight - el.scrollTop - el.clientHeight
  );

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const wasScrollingDown = el.scrollTop > lastScrollTopRef.current;
    lastScrollTopRef.current = el.scrollTop;
    const distance = getDistanceToBottom(el);
    if (wasScrollingDown && distance <= RELOCK_THRESHOLD_PX) {
      manuallyUnlockedRef.current = false;
      setAutoScrollEnabled(true);
    }
  };

  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (e.deltaY < 0) {
      manuallyUnlockedRef.current = true;
      setAutoScrollEnabled(false);
    }
  };

  const scrollToBottom = () => {
    manuallyUnlockedRef.current = false;
    setAutoScrollEnabled(true);
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  };

  const scheduleScrollToBottom = (behavior: ScrollBehavior) => {
    if (scrollFrameRef.current != null) return;
    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      bottomRef.current?.scrollIntoView({ behavior, block: "end" });
    });
  };

  useEffect(() => () => {
    if (scrollFrameRef.current != null) {
      window.cancelAnimationFrame(scrollFrameRef.current);
    }
  }, []);

  useEffect(() => {
    if (selectedSessionId) {
      manuallyUnlockedRef.current = false;
      setAutoScrollEnabled(true);
      loadTimeline(selectedSessionId);
    }
  }, [selectedSessionId, loadTimeline]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    lastScrollTopRef.current = el.scrollTop;
    scheduleScrollToBottom("auto");
  }, [selectedSessionId]);

  useEffect(() => {
    if (loadingTimeline || !selectedSessionId) return;
    if (!autoScrollEnabled) return;
    scheduleScrollToBottom("auto");
  }, [loadingTimeline, selectedSessionId, autoScrollEnabled]);

  useEffect(() => {
    if (!autoScrollEnabled) return;
    scheduleScrollToBottom("auto");
  }, [currentContent, currentReasoning, currentToolCalls, autoScrollEnabled]);

  useEffect(() => {
    if (!autoScrollEnabled) return;
    scheduleScrollToBottom("smooth");
  }, [timeline.length, busy, autoScrollEnabled]);

  useEffect(() => {
    if (!focusedToolCallId) return;
    const target = document.getElementById(`tool-call-${focusedToolCallId}`);
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = window.setTimeout(() => focusToolCall(null), 2200);
    return () => window.clearTimeout(timer);
  }, [focusedToolCallId, timelineSource, focusToolCall]);

  if (!selectedSessionId) {
    return (
      <div className="flex-1 min-h-0 grid place-items-center p-4">
        <EmptyState
          title="暂无会话"
          description="创建账户和 Session 后，这里会显示对话消息、工具调用与工具结果。"
        />
      </div>
    );
  }

  if (loadingTimeline) {
    return (
      <div className="flex-1 min-h-0 grid place-items-center p-4">
        <Spinner size={24} />
      </div>
    );
  }

  if (timeline.length === 0 && !busy) {
    return (
      <div className="flex-1 min-h-0 grid place-items-center p-4">
        <EmptyState
          title="暂无消息"
          description="发送消息或运行 Session 后，这里会显示对话消息。"
        />
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 relative">
      <div className="h-full overflow-y-auto" ref={scrollRef} onScroll={handleScroll} onWheel={handleWheel}>
        <div className="flex flex-col gap-3 p-4 min-h-full">
          {timeline.map((item) => {
            const highlighted = Boolean(item.toolCallId && item.toolCallId === focusedToolCallId);
            return (
              <div
                key={item.id}
                id={item.toolCallId ? `tool-call-${item.toolCallId}` : undefined}
                className={highlighted ? "rounded-lg bg-brand-primary/10 ring-1 ring-brand-primary/60 transition-colors" : undefined}
              >
                <MessageBubble item={item} />
              </div>
            );
          })}
          {busy && !loadingTimeline && !currentContent && !currentReasoning && <LoadingDots />}
          <div ref={bottomRef} />
        </div>
      </div>
      {!autoScrollEnabled && (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute right-4 bottom-4 z-10 rounded-full border border-hairline bg-surface-elevated px-3 py-1.5 text-xs text-text-muted-strong shadow-lg hover:bg-surface-card transition-colors"
        >
          回到底部
        </button>
      )}
    </div>
  );
}
