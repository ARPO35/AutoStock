import { create } from "zustand";
import type {
  MarketQuote,
  MarketHistoryResponse,
  FetchHistoryResponse,
  CacheStatusRow,
  DataConflict
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

  setMarketForm: (value: typeof defaultMarketForm) => void;
  setDataFetchForm: (value: typeof defaultDataFetchForm) => void;

  queryQuote: (symbol: string) => Promise<void>;
  queryHistory: (symbol: string, start?: string, end?: string, adjust?: string, allowFetchMissing?: boolean) => Promise<void>;
  fetchHistory: (symbol: string, start: string, end: string, adjust?: string) => Promise<void>;
  loadDataState: () => Promise<void>;
  resolveConflict: (id: string, status: "resolved" | "ignored") => Promise<void>;
}

export const useMarketStore = create<MarketState>((set) => ({
  marketForm: { ...defaultMarketForm },
  marketQuote: null,
  marketHistory: null,
  cacheRows: [],
  dataFetchForm: { ...defaultDataFetchForm },
  dataFetchResult: null,
  conflicts: [],

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
      const [rows, c] = await Promise.all([api.cacheStatus(), api.dataConflicts("open")]);
      set({ cacheRows: rows, conflicts: c });
    } catch {
      // handled by ui store
    }
  },

  resolveConflict: async (id, status) => {
    await api.resolveConflict(id, status);
    const c = await api.dataConflicts("open");
    set({ conflicts: c });
  }
}));
