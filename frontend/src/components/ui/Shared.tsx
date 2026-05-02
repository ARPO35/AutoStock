import type { ReactNode } from "react";

export function Metric({
  label,
  value,
  tone
}: {
  label: string;
  value: string;
  tone?: "rise" | "fall" | "flat";
}) {
  return (
    <div className="p-2.5 border border-hairline rounded-lg bg-surface-canvas/50">
      <span className="block text-xs text-text-muted">{label}</span>
      <strong
        className={
          tone === "rise"
            ? "rise block mt-1 text-[15px]"
            : tone === "fall"
              ? "fall block mt-1 text-[15px]"
              : "block mt-1 text-[15px] text-text-on-dark"
        }
      >
        {value}
      </strong>
    </div>
  );
}

export function InfoGrid({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {items.length === 0 ? (
        <div className="p-2 border border-hairline rounded-lg bg-surface-canvas/40">
          <span className="block text-xs text-text-muted">数据</span>
          <strong className="block mt-1 text-text-on-dark truncate">--</strong>
        </div>
      ) : (
        items.map(([label, value]) => (
          <div key={`${label}-${value}`} className="p-2 border border-hairline rounded-lg bg-surface-canvas/40 min-w-0">
            <span className="block text-xs text-text-muted">{label}</span>
            <strong className="block mt-1 text-text-on-dark truncate">{value}</strong>
          </div>
        ))
      )}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="grid place-items-center content-center gap-2 min-h-[120px] p-4 border border-dashed border-hairline rounded-lg text-text-muted text-center">
      <strong className="text-text-on-dark">{title}</strong>
      <span className="max-w-[420px] leading-relaxed text-sm">{description}</span>
    </div>
  );
}

export function Badge({ children, variant = "default" }: { children: ReactNode; variant?: "default" | "running" | "error" | "queued" }) {
  const colors = {
    default: "border-hairline bg-surface-elevated text-text-on-dark",
    running: "border-accent-turquoise/30 text-accent-turquoise",
    error: "border-trading-rise/30 text-trading-rise",
    queued: "border-brand-primary/30 text-brand-primary"
  };

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 border rounded-full text-xs ${colors[variant]}`}>
      {children}
    </span>
  );
}

export function PanelHeader({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <header className="flex items-center gap-2 mb-2.5 text-text-muted-strong">
      {icon}
      <h3 className="m-0 text-sm font-semibold">{title}</h3>
    </header>
  );
}

export function RawJson({ data }: { data: Record<string, unknown> }) {
  return (
    <details className="mt-2 text-text-muted">
      <summary className="cursor-pointer text-brand-primary text-sm">查看原始 JSON</summary>
      <pre className="mt-2 p-2.5 rounded-lg bg-surface-canvas text-text-body text-xs whitespace-pre-wrap break-all font-mono">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

export function SubTabs({ tabs, active, onChange }: { tabs: string[]; active: string; onChange: (tab: string) => void }) {
  return (
    <nav className="flex gap-1.5 mb-2.5 p-1 border border-hairline rounded-xl bg-surface-canvas/60 overflow-x-auto">
      {tabs.map((tab) => (
        <button
          className={`min-h-[30px] px-3 rounded-lg text-sm whitespace-nowrap transition-colors ${
            active === tab
              ? "text-text-on-dark bg-surface-elevated shadow-[inset_0_-2px_0_#fcd535]"
              : "text-text-muted hover:text-text-on-dark"
          }`}
          key={tab}
          onClick={() => onChange(tab)}
          type="button"
        >
          {tab}
        </button>
      ))}
    </nav>
  );
}
