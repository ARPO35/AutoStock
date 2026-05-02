import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useTradeStore } from "@/stores/tradeStore";
import { EmptyState } from "@/components/ui/Shared";
import { TimelineCard } from "@/features/trade/TimelineCard";

export function LLMLinearTimeline() {
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const getTimeline = useTradeStore((s) => s.getTimeline);
  const timeline = getTimeline();

  const scrollRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: timeline.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 120,
    overscan: 5
  });

  if (!selectedSessionId) {
    return (
      <div className="min-h-0 overflow-auto p-4 grid place-items-center">
        <EmptyState
          title="暂无会话"
          description="创建账户和 Session 后，这里会显示真实消息、工具调用与工具结果。"
        />
      </div>
    );
  }

  if (timeline.length === 0) {
    return (
      <div className="min-h-0 overflow-auto p-4 grid place-items-center">
        <EmptyState
          title="暂无消息"
          description="发送消息或运行 Session 后，这里会显示真实执行链。"
        />
      </div>
    );
  }

  return (
    <div className="relative min-h-0 overflow-auto py-4 px-3.5" ref={scrollRef}>
      <div
        className="absolute left-[80px] top-5 bottom-5 w-px"
        style={{
          background:
            "linear-gradient(180deg, transparent, rgba(113, 166, 233, 0.5), transparent)"
        }}
      />
      <div
        className="relative"
        style={{ height: `${virtualizer.getTotalSize()}px` }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const item = timeline[virtualRow.index];
          return (
            <div
              key={virtualRow.key}
              className="absolute top-0 left-0 w-full"
              style={{
                height: `${virtualRow.size}px`,
                transform: `translateY(${virtualRow.start}px)`
              }}
            >
              <TimelineCard item={item} index={virtualRow.index} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
