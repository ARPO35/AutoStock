import { ChevronRight } from "lucide-react";
import type { TimelineItem } from "@/types";
import { toolDisplayName, summarizeArgsChinese } from "@/lib/utils";
import { ToolResultRenderer } from "@/features/trade/ToolResultRenderer";

export function ToolCallCard({ item }: { item: TimelineItem }) {
  const displayName = toolDisplayName(item.toolName);
  const args = summarizeArgsChinese(
    (item.raw as Record<string, unknown> | undefined)?.arguments_json as string ?? null
  );
  const hasError = item.status === "error";
  const hasResult = item.result !== undefined && item.result !== null;

  return (
    <details className="group/tc">
      <summary className="flex items-center gap-1.5 cursor-pointer text-text-muted text-xs hover:text-text-muted-strong list-none select-none">
        <ChevronRight size={13} className="transition-transform group-open/tc:rotate-90" />
        <span className="text-text-muted-strong">{displayName}</span>
        <span>{args}</span>
        {hasError && <span className="text-trading-rise ml-1">失败</span>}
        {item.status === "finished" && !item.result && <span className="text-trading-fall ml-1">已完成</span>}
      </summary>
      <div className="ml-3 pl-3 border-l border-hairline mt-1 py-1">
        {hasError ? (
          <p className="text-trading-rise text-xs">{item.body || "工具执行失败"}</p>
        ) : hasResult ? (
          <ToolResultRenderer payload={item.result!} toolName={item.toolName} />
        ) : item.status === "finished" ? (
          <p className="text-text-muted text-xs">已完成</p>
        ) : (
          <p className="text-text-muted text-xs">执行中...</p>
        )}
      </div>
    </details>
  );
}
