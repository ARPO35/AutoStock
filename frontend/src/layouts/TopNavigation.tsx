import { UserRound } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import type { NavItem } from "@/types";
import { useDataStore } from "@/stores/dataStore";

const navItems: NavItem[] = [
  { key: "trade", label: "交易（LLM）", sub: "WebChat 工作台" },
  { key: "view", label: "查看", sub: "全局观察" },
  { key: "edit", label: "修改", sub: "审计修改" },
  { key: "manage", label: "管理", sub: "能力配置" }
];

export function TopNavigation() {
  const location = useLocation();
  const reactRouterNavigate = useNavigate();
  const route = location.pathname.split("/").filter(Boolean)[0] || "trade";
  const providerCount = useDataStore((s) => s.providers.length);
  const selectedSessionId = useDataStore((s) => s.sessions.length > 0);

  return (
    <header className="h-16 flex items-center gap-5 px-4 border-b border-hairline bg-surface-canvas">
      {/* Brand */}
      <button
        className="inline-flex items-center gap-3 bg-transparent text-left min-w-[220px]"
        type="button"
        onClick={() => reactRouterNavigate("/trade")}
      >
        <span className="w-8 h-8 grid place-items-center rounded-lg bg-brand-primary text-brand-ink font-bold text-lg">
          A
        </span>
        <span>
          <strong className="block text-base tracking-wide">A股 LLM 交易系统</strong>
          <small className="text-text-muted text-xs">模拟盘 · 可见推理 · 工具追踪</small>
        </span>
      </button>

      {/* Primary Tabs */}
      <nav className="h-10 grid grid-cols-4 border border-hairline rounded-xl bg-surface-card overflow-hidden flex-1 max-w-[520px]">
        {navItems.map((item) => (
          <TabButton
            key={item.key}
            active={route === item.key}
            label={item.label}
            sub={item.sub}
            onClick={() => reactRouterNavigate(`/${item.key}`)}
          />
        ))}
      </nav>

      {/* Meta */}
      <div className="ml-auto inline-flex items-center gap-2.5 text-text-muted text-xs">
        <span>{providerCount > 0 ? `${providerCount} Provider` : "未配置"}</span>
        <span>{selectedSessionId ? "已选择" : "暂无会话"}</span>
        <span className="w-7 h-7 grid place-items-center rounded-full bg-surface-card border border-hairline">
          <UserRound size={14} />
        </span>
      </div>
    </header>
  );
}

function TabButton({ active, label, sub, onClick }: { active: boolean; label: string; sub: string; onClick: () => void }) {
  return (
    <button
      className={`relative grid place-items-center content-center gap-0.5 text-sm transition-colors ${
        active
          ? "text-text-on-dark bg-brand-primary/10"
          : "text-text-muted hover:text-text-on-dark"
      }`}
      onClick={onClick}
      type="button"
    >
      <span className={active ? "font-semibold" : ""}>{label}</span>
      <small className="text-[11px] text-text-muted">{sub}</small>
      {active && (
        <span className="absolute bottom-0 left-[20%] right-[20%] h-0.5 bg-brand-primary" />
      )}
    </button>
  );
}
