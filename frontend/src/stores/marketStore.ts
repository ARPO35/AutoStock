import { create } from "zustand";
import type {
  MarketQuote,
  MarketHistoryResponse,
  FetchHistoryResponse,
  CacheStatusRow,
  DataConflict,
  MarketWatchlistItem,
  MarketSyncRun
} from "@/api";
import { api } from "@/api";

const defaultMarketForm = { symbol: "", start: "", end: "", adjust: "", allowFetchMissing: false };
const defaultDataFetchForm = { symbol: "", start: "", end: "", adjust: "" };

interface MarketState {
  marketForm: typeof defaultMarketForm;
  marketQuote: MarketQuote | null;
  marketHistory: MarketHistoryResponse | null;
  cacheRows: CacheStatusRow[];
  dataFetchForm: typeof defaultDataFetchForm;
  dataFetchResult: FetchHistoryResponse | null;
  conflicts: DataConflict[];
  watchlist: MarketWatchlistItem[];
  syncRuns: MarketSyncRun[];
  syncBusy: boolean;

  setMarketForm: (value: typeof defaultMarketForm) => void;
  setDataFetchForm: (value: typeof defaultDataFetchForm) => void;

  queryQuote: (symbol: string) => Promise<void>;
  queryHistory: (symbol: string, start?: string, end?: string, adjust?: string, allowFetchMissing?: boolean) => Promise<void>;
  fetchHistory: (symbol: string, start: string, end: string, adjust?: string) => Promise<void>;
  loadDataState: () => Promise<void>;
  resolveConflict: (id: string, status: "resolved" | "ignored") => Promise<void>;
  addWatchlistSymbol: (symbol: string, name?: string, note?: string) => Promise<void>;
  updateWatchlistSymbol: (id: string, enabled: boolean) => Promise<void>;
  deleteWatchlistSymbol: (id: string) => Promise<void>;
  runMarketSync: (jobType: string, scope?: string) => Promise<void>;
}

export const useMarketStore = create<MarketState>((set) => ({
  marketForm: { ...defaultMarketForm },
  marketQuote: null,
  marketHistory: null,
  cacheRows: [],
  dataFetchForm: { ...defaultDataFetchForm },
  dataFetchResult: null,
  conflicts: [],
  watchlist: [],
  syncRuns: [],
  syncBusy: false,

  setMarketForm: (value) => set({ marketForm: value }),
  setDataFetchForm: (value) => set({ dataFetchForm: value }),

  queryQuote: async (symbol) => {
    set({ marketQuote: await api.quote(symbol) });
  },

  queryHistory: async (symbol, start, end, adjust, allowFetchMissing) => {
    set({
      marketHistory: await api.history({
        symbol,
        start,
        end,
        interval: "daily",
        adjust,
        allowFetchMissing
      })
    });
  },

  fetchHistory: async (symbol, start, end, adjust) => {
    set({
      dataFetchResult: await api.fetchHistory({
        symbol,
        start,
        end,
        interval: "daily",
        adjust
      })
    });
    await api.cacheStatus().then((rows) => set({ cacheRows: rows })).catch(() => {});
  },

  loadDataState: async () => {
    try {
      const [rows, c, watchlist, syncRuns] = await Promise.all([
        api.cacheStatus(),
        api.dataConflicts("open"),
        api.watchlist(),
        api.syncRuns(10)
      ]);
      set({ cacheRows: rows, conflicts: c, watchlist, syncRuns });
    } catch {
      // handled by ui store
    }
  },

  resolveConflict: async (id, status) => {
    await api.resolveConflict(id, status);
    const c = await api.dataConflicts("open");
    set({ conflicts: c });
  },

  addWatchlistSymbol: async (symbol, name, note) => {
    await api.addWatchlistSymbol({ symbol, name, note });
    const watchlist = await api.watchlist();
    set({ watchlist });
  },

  updateWatchlistSymbol: async (id, enabled) => {
    await api.updateWatchlistSymbol(id, { enabled });
    const watchlist = await api.watchlist();
    set({ watchlist });
  },

  deleteWatchlistSymbol: async (id) => {
    await api.deleteWatchlistSymbol(id);
    const watchlist = await api.watchlist();
    set({ watchlist });
  },

  runMarketSync: async (jobType, scope = "all") => {
    set({ syncBusy: true });
    try {
      await api.runMarketSync({ job_type: jobType, scope });
      const [syncRuns, cacheRows] = await Promise.all([api.syncRuns(10), api.cacheStatus()]);
      set({ syncRuns, cacheRows });
    } finally {
      set({ syncBusy: false });
    }
  }
}));
