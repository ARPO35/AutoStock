import { useEffect, useRef } from "react";
import { useTradeStore } from "@/stores/tradeStore";
import { EmptyState, LoadingDots } from "@/components/ui/Shared";
import { MessageBubble } from "@/features/trade/MessageBubble";

export function LLMLinearTimeline() {
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const getTimeline = useTradeStore((s) => s.getTimeline);
  const busy = useTradeStore((s) => s.busy);
  const optimisticUserMessage = useTradeStore((s) => s.optimisticUserMessage);
  const timeline = getTimeline();

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [timeline.length, optimisticUserMessage, busy]);

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

  if (timeline.length === 0 && !busy) {
    return (
      <div className="flex-1 min-h-0 grid place-items-center p-4">
        <EmptyState
          title="暂无消息"
          description="发送消息或运行 Session 后，这里会显示真实执行链。"
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
        {busy && <LoadingDots />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
