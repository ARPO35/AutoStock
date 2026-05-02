import { useEffect, useMemo, useRef } from "react";
import { useTradeStore } from "@/stores/tradeStore";
import { EmptyState, LoadingDots, Spinner } from "@/components/ui/Shared";
import { MessageBubble } from "@/features/trade/MessageBubble";

export function LLMLinearTimeline() {
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const loadTimeline = useTradeStore((s) => s.loadTimeline);
  const busy = useTradeStore((s) => s.busy);
  const loadingTimeline = useTradeStore((s) => s.loadingTimeline);

  // 订阅 getTimeline() 依赖的原始字段，避免无限重渲染
  const timelineSource = useTradeStore((s) => s.timelineSource);
  const streamingContent = useTradeStore((s) => s.streamingContent);
  const streamingReasoning = useTradeStore((s) => s.streamingReasoning);
  const optimisticUserMessage = useTradeStore((s) => s.optimisticUserMessage);
  const lastModel = useTradeStore((s) => s.lastModel);
  const lastRunLatencyMs = useTradeStore((s) => s.lastRunLatencyMs);

  const timeline = useMemo(
    () => useTradeStore.getState().getTimeline(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [timelineSource, streamingContent, streamingReasoning, optimisticUserMessage, lastModel, lastRunLatencyMs]
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selectedSessionId) {
      loadTimeline(selectedSessionId);
    }
  }, [selectedSessionId, loadTimeline]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [timeline.length, busy, streamingContent]);

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
    <div className="flex-1 min-h-0 overflow-y-auto" ref={scrollRef}>
      <div className="flex flex-col gap-3 p-4 min-h-full">
        {timeline.map((item) => (
          <MessageBubble key={item.id} item={item} />
        ))}
        {busy && !loadingTimeline && <LoadingDots />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
