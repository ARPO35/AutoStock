import type { TimelineItem } from "@/types";
import { InfoGrid, RawJson } from "@/components/ui/Shared";

export function ToolCallCard({ item }: { item: TimelineItem }) {
  return (
    <details className="mt-2">
      <summary className="grid grid-cols-[minmax(150px,1fr)_minmax(140px,1.1fr)_auto] gap-2.5 items-center cursor-pointer p-2 border border-hairline rounded-lg bg-surface-canvas/40 list-none">
        <span className="text-text-on-dark text-sm">
          [Tool Call] {item.toolName ?? "unknown"}
        </span>
        <small className="text-text-muted text-xs truncate">
          {item.argsSummary}
        </small>
        <span className="text-text-muted text-xs">{item.status ?? "--"}</span>
      </summary>
      <div className="mt-2 p-2.5 border border-hairline rounded-lg bg-surface-canvas/30">
        <InfoGrid
          items={[
            ["调用工具", item.toolName ?? "--"],
            ["调用状态", item.status ?? "--"],
            ["参数摘要", item.argsSummary ?? "--"]
          ]}
        />
        {item.raw && <RawJson data={item.raw} />}
      </div>
    </details>
  );
}
