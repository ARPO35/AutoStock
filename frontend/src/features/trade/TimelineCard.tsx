import {
  Clock3,
  UserRound,
  Bot,
  Wrench,
  CheckCircle2,
  AlertTriangle,
  Zap
} from "lucide-react";
import type { TimelineItem } from "@/types";
import { ToolCallCard } from "@/features/trade/ToolCallCard";
import { ToolResultRenderer } from "@/features/trade/ToolResultRenderer";
import { RawJson } from "@/components/ui/Shared";

export function TimelineCard({ item, index }: { item: TimelineItem; index: number }) {
  return (
    <article
      className="relative grid grid-cols-[76px_28px_minmax(0,1fr)] gap-2 mb-3 opacity-0 animate-reveal"
      style={{ animationDelay: `${Math.min(index * 45, 420)}ms` }}
    >
      <div className="inline-flex items-center gap-1 text-text-muted text-xs pt-2.5">
        <Clock3 size={13} />
        {item.time}
      </div>
      <div className="w-7 h-7 grid place-items-center rounded-full border border-hairline bg-surface-elevated text-brand-primary z-10 flex-shrink-0">
        <TimelineIcon kind={item.kind} />
      </div>
      <div className="p-3 border border-hairline rounded-lg bg-surface-card">
        <header className="flex items-center justify-between gap-2.5 mb-2">
          <span className="text-sm font-semibold text-text-on-dark">
            {item.title}
          </span>
          {item.toolName && (
            <code className="text-brand-primary bg-brand-primary/10 px-1.5 py-0.5 rounded text-xs">
              {item.toolName}
            </code>
          )}
        </header>
        {item.kind === "tool-call" && <ToolCallCard item={item} />}
        {item.result && (
          <ToolResultRenderer
            payload={item.result}
            toolName={item.toolName}
            raw={item.raw}
          />
        )}
        {item.body && (
          <p className="text-text-body leading-relaxed text-sm mt-1 mb-0">
            {item.body}
          </p>
        )}
        {item.raw && item.kind !== "tool-call" && <RawJson data={item.raw} />}
      </div>
    </article>
  );
}

function TimelineIcon({ kind }: { kind: TimelineItem["kind"] }) {
  const size = 14;
  if (kind === "user") return <UserRound size={size} />;
  if (kind === "event") return <Zap size={size} />;
  if (kind === "assistant") return <Bot size={size} />;
  if (kind === "tool-call") return <Wrench size={size} />;
  if (kind === "tool-result") return <CheckCircle2 size={size} />;
  return <AlertTriangle size={size} />;
}
