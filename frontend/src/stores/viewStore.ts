import { create } from "zustand";
import { api } from "@/api";
import type {
  AccountSnapshot,
  ViewAccountsResponse,
  ViewAssetsResponse,
  ViewFilters,
  ViewLogsResponse,
  ViewOverviewResponse,
  ViewTimelineResponse,
  ViewTradesResponse
} from "@/api";

interface ViewState {
  filters: ViewFilters;
  loading: boolean;
  error: string | null;
  overview: ViewOverviewResponse | null;
  accounts: ViewAccountsResponse | null;
  trades: ViewTradesResponse | null;
  assets: ViewAssetsResponse | null;
  logs: ViewLogsResponse | null;
  timeline: ViewTimelineResponse | null;
  snapshots: Record<string, AccountSnapshot>;

  setFilters: (filters: ViewFilters) => void;
  patchFilters: (patch: Partial<ViewFilters>) => void;
  loadOverview: () => Promise<void>;
  loadAccounts: () => Promise<void>;
  loadTrades: () => Promise<void>;
  loadAssets: () => Promise<void>;
  loadLogs: () => Promise<void>;
  loadTimeline: () => Promise<void>;
  loadSnapshot: (accountId: string) => Promise<AccountSnapshot | null>;
  refreshCurrent: (section: ViewSection) => Promise<void>;
}

export type ViewSection =
  | "overview"
  | "account-detail"
  | "trades"
  | "assets"
  | "stock"
  | "logs"
  | "timeline";

export const viewSections: Array<{ key: ViewSection; label: string; sub: string }> = [
  { key: "overview", label: "总览", sub: "账户与风险面" },
  { key: "account-detail", label: "账号详情", sub: "资金、持仓、会话" },
  { key: "trades", label: "交易历史", sub: "订单与成交" },
  { key: "assets", label: "资产曲线", sub: "净值与仓位" },
  { key: "stock", label: "股票信息", sub: "行情与缓存" },
  { key: "logs", label: "决策日志", sub: "交易理由" },
  { key: "timeline", label: "时间线", sub: "全局事件流" }
];

export const useViewStore = create<ViewState>((set, get) => ({
  filters: {},
  loading: false,
  error: null,
  overview: null,
  accounts: null,
  trades: null,
  assets: null,
  logs: null,
  timeline: null,
  snapshots: {},

  setFilters: (filters) => set({ filters }),
  patchFilters: (patch) =>
    set((state) => ({
      filters: {
        ...state.filters,
        ...patch,
        account_id: patch.account_id === "" ? undefined : patch.account_id ?? state.filters.account_id,
        session_id: patch.session_id === "" ? undefined : patch.session_id ?? state.filters.session_id,
        model: patch.model === "" ? undefined : patch.model ?? state.filters.model,
        symbol: patch.symbol === "" ? undefined : patch.symbol ?? state.filters.symbol,
        side: patch.side === "" ? undefined : patch.side ?? state.filters.side,
        status: patch.status === "" ? undefined : patch.status ?? state.filters.status,
        time_scope: patch.time_scope ?? state.filters.time_scope,
        start: patch.start === "" ? undefined : patch.start ?? state.filters.start,
        end: patch.end === "" ? undefined : patch.end ?? state.filters.end,
      }
    })),

  loadOverview: async () => {
    await load(set, async () => set({ overview: await api.viewOverview(get().filters) }));
  },
  loadAccounts: async () => {
    await load(set, async () => set({ accounts: await api.viewAccounts(get().filters) }));
  },
  loadTrades: async () => {
    await load(set, async () => set({ trades: await api.viewTrades({ ...get().filters, limit: 500 }) }));
  },
  loadAssets: async () => {
    await load(set, async () => set({ assets: await api.viewAssets(get().filters) }));
  },
  loadLogs: async () => {
    await load(set, async () => set({ logs: await api.viewLogs({ ...get().filters, limit: 500 }) }));
  },
  loadTimeline: async () => {
    await load(set, async () => set({ timeline: await api.viewTimeline({ ...get().filters, limit: 600 }) }));
  },
  loadSnapshot: async (accountId) => {
    let snapshot: AccountSnapshot | null = null;
    await load(set, async () => {
      snapshot = await api.accountSnapshot(accountId, {
        start: get().filters.start,
        end: get().filters.end,
        symbol: get().filters.symbol
      });
      set((state) => ({ snapshots: { ...state.snapshots, [accountId]: snapshot as AccountSnapshot } }));
    });
    return snapshot;
  },
  refreshCurrent: async (section) => {
    const state = get();
    if (section === "overview") return state.loadOverview();
    if (section === "account-detail") return state.loadAccounts();
    if (section === "trades") return state.loadTrades();
    if (section === "assets") return state.loadAssets();
    if (section === "logs") return state.loadLogs();
    if (section === "timeline") return state.loadTimeline();
  }
}));

async function load(
  set: (partial: Partial<ViewState> | ((state: ViewState) => Partial<ViewState>)) => void,
  action: () => Promise<void>
) {
  set({ loading: true, error: null });
  try {
    await action();
    set({ loading: false });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    set({ loading: false, error: message });
  }
}
