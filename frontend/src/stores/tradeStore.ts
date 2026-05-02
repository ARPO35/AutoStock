import { create } from "zustand";
import type { SessionTimelineItem, RuntimeEvent } from "@/api";
import type { TimelineItem } from "@/types";
import { api } from "@/api";
import { buildTimeline } from "@/lib/utils";

interface TradeState {
  selectedSessionId: string;
  timelineSource: SessionTimelineItem[];
  events: RuntimeEvent[];
  draft: string;
  busy: boolean;

  setSelectedSessionId: (id: string) => void;
  setDraft: (value: string) => void;
  setBusy: (value: boolean) => void;
  setEvents: (events: RuntimeEvent[]) => void;
  pushEvent: (event: RuntimeEvent) => void;

  loadTimeline: (sessionId: string) => Promise<void>;
  sendMessage: (sessionId: string, mode: "run" | "event" | "write", content: string) => Promise<void>;
  runOnce: (sessionId: string) => Promise<void>;

  getTimeline: () => TimelineItem[];
}

export const useTradeStore = create<TradeState>((set, get) => ({
  selectedSessionId: "",
  timelineSource: [],
  events: [],
  draft: "",
  busy: false,

  setSelectedSessionId: (id) => set({ selectedSessionId: id }),
  setDraft: (value) => set({ draft: value }),
  setBusy: (value) => set({ busy: value }),
  setEvents: (events) => set({ events }),

  pushEvent: (event) =>
    set((s) => ({ events: [event, ...s.events].slice(0, 60) })),

  loadTimeline: async (sessionId) => {
    try {
      set({ timelineSource: await api.sessionTimeline(sessionId) });
    } catch {
      // handled by ui store
    }
  },

  sendMessage: async (sessionId, mode, content) => {
    set({ draft: "", busy: true });
    try {
      if (mode === "write") {
        await api.createMessage(sessionId, { role: "user", content, message_type: "user" });
      } else {
        await api.runSession(sessionId, {
          message: mode === "event" ? `[手动事件]\n${content}` : content,
          max_tool_rounds: 5
        });
      }
      await get().loadTimeline(sessionId);
    } finally {
      set({ busy: false });
    }
  },

  runOnce: async (sessionId) => {
    set({ busy: true });
    try {
      await api.runSession(sessionId, { max_tool_rounds: 5 });
      await get().loadTimeline(sessionId);
    } finally {
      set({ busy: false });
    }
  },

  getTimeline: () => buildTimeline(get().timelineSource)
}));
