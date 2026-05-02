import type { TimelineItem } from "@/types";
import { ToolCallCard } from "@/features/trade/ToolCallCard";
import { ToolResultRenderer } from "@/features/trade/ToolResultRenderer";

export function MessageBubble({ item }: { item: TimelineItem }) {
  if (item.role === "user") return <UserBubble item={item} />;
  if (item.role === "assistant") return <AssistantBubble item={item} />;
  if (item.role === "tool-call") return <ToolCallBubble item={item} />;
  if (item.role === "tool-result") return <ToolResultBubble item={item} />;
  if (item.role === "event") return <EventBubble item={item} />;
  return <ErrorBubble item={item} />;
}

function UserBubble({ item }: { item: TimelineItem }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-brand-primary/10 rounded-2xl rounded-br-md px-4 py-3">
        <p className="text-text-body text-sm leading-relaxed whitespace-pre-wrap break-words">
          {item.body || ""}
        </p>
        <span className="block text-text-muted text-[11px] mt-1.5 text-right">
          {item.time}
        </span>
      </div>
    </div>
  );
}

function AssistantBubble({ item }: { item: TimelineItem }) {
  const model = item.model || "--";
  const latency = item.latencyMs != null ? formatLatency(item.latencyMs) : "--";
  const tps = item.tps != null ? formatTps(item.tps) : "--";
  const tokens = item.tokenCount != null ? formatTokens(item.tokenCount) : "--";

  return (
    <div className="flex justify-start">
      <div className="max-w-[75%] bg-surface-card rounded-2xl rounded-bl-md px-4 py-3">
        <p className="text-text-body text-sm leading-relaxed whitespace-pre-wrap break-words">
          {item.body || (item.streaming ? "..." : "")}
        </p>
        <div className="flex items-center gap-1 mt-1.5 text-text-muted text-[11px] select-none">
          <span>{item.time || "--"}</span>
          {item.time && <span className="text-hairline">·</span>}
          <span>{model}</span>
          <span className="text-hairline">·</span>
          <span>{latency}</span>
          <span className="text-hairline">·</span>
          <span>{tps}</span>
          <span className="text-hairline">·</span>
          <span>{tokens}</span>
        </div>
      </div>
    </div>
  );
}

function ToolCallBubble({ item }: { item: TimelineItem }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md">
        <ToolCallCard item={item} />
      </div>
    </div>
  );
}

function ToolResultBubble({ item }: { item: TimelineItem }) {
  if (!item.result) return null;
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md">
        <ToolResultRenderer
          payload={item.result}
          toolName={item.toolName}
        />
      </div>
    </div>
  );
}

function EventBubble({ item }: { item: TimelineItem }) {
  return (
    <div className="flex justify-center">
      <span className="inline-block px-3 py-1 rounded-full bg-surface-elevated/50 text-text-muted text-xs">
        {item.body || item.title}
      </span>
    </div>
  );
}

function ErrorBubble({ item }: { item: TimelineItem }) {
  return (
    <div className="flex justify-center">
      <div className="max-w-[75%] bg-trading-rise/10 border border-trading-rise/30 rounded-lg px-3 py-2">
        <p className="text-trading-rise text-xs leading-relaxed whitespace-pre-wrap break-words">
          {item.body || item.title}
        </p>
      </div>
    </div>
  );
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTps(tps: number): string {
  if (!Number.isFinite(tps) || tps <= 0) return "--";
  if (tps < 100) return `${tps.toFixed(1)} t/s`;
  return `${Math.round(tps)} t/s`;
}

function formatTokens(count: number): string {
  if (!Number.isFinite(count) || count < 0) return "--";
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return String(Math.round(count));
}
