import { create } from "zustand";
import type { SessionTimelineItem, RuntimeEvent } from "@/api";
import type { TimelineItem } from "@/types";
import { api } from "@/api";
import { buildTimeline, humanTime } from "@/lib/utils";

interface TradeState {
  selectedSessionId: string;
  timelineSource: SessionTimelineItem[];
  events: RuntimeEvent[];
  draft: string;
  busy: boolean;

  optimisticUserMessage: string | null;
  streamingContent: string | null;
  lastModel: string | null;
  lastRunLatencyMs: number | null;

  setSelectedSessionId: (id: string) => void;
  setDraft: (value: string) => void;
  setBusy: (value: boolean) => void;
  setEvents: (events: RuntimeEvent[]) => void;
  pushEvent: (event: RuntimeEvent) => void;

  loadTimeline: (sessionId: string) => Promise<void>;
  sendMessage: (sessionId: string, mode: "run" | "event" | "write", content: string, model?: string | null) => Promise<void>;
  runOnce: (sessionId: string, model?: string | null) => Promise<void>;

  getTimeline: () => TimelineItem[];
}

function syntheticUserMessage(content: string): TimelineItem {
  return {
    id: `opt-${Date.now()}`,
    kind: "user",
    role: "user",
    time: humanTime(new Date().toISOString()),
    title: "用户",
    body: content
  };
}

function syntheticAssistantMessage(content: string, model: string | null): TimelineItem {
  return {
    id: "streaming",
    kind: "assistant",
    role: "assistant",
    time: "",
    title: "助手",
    body: content,
    model,
    streaming: true
  };
}

export const useTradeStore = create<TradeState>((set, get) => ({
  selectedSessionId: "",
  timelineSource: [],
  events: [],
  draft: "",
  busy: false,

  optimisticUserMessage: null,
  streamingContent: null,
  lastModel: null,
  lastRunLatencyMs: null,

  setSelectedSessionId: (id) =>
    set({
      selectedSessionId: id,
      optimisticUserMessage: null,
      streamingContent: null
    }),
  setDraft: (value) => set({ draft: value }),
  setBusy: (value) => set({ busy: value }),
  setEvents: (events) => set({ events }),

  pushEvent: (event) =>
    set((s) => ({ events: [event, ...s.events].slice(0, 60) })),

  loadTimeline: async (sessionId) => {
    try {
      const source = await api.sessionTimeline(sessionId);
      set({
        timelineSource: source,
        optimisticUserMessage: null,
        streamingContent: null
      });
    } catch {
      // 由 ui store 处理
    }
  },

  sendMessage: async (sessionId, mode, content, model) => {
    const t0 = Date.now();
    set({
      draft: "",
      busy: true,
      optimisticUserMessage: content,
      streamingContent: null,
      lastModel: model ?? null,
      lastRunLatencyMs: null
    });
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
      set({ lastRunLatencyMs: Date.now() - t0 });
    } finally {
      set({ busy: false });
    }
  },

  runOnce: async (sessionId, model) => {
    const t0 = Date.now();
    set({
      busy: true,
      optimisticUserMessage: null,
      streamingContent: null,
      lastModel: model ?? null,
      lastRunLatencyMs: null
    });
    try {
      await api.runSession(sessionId, { max_tool_rounds: 5 });
      await get().loadTimeline(sessionId);
      set({ lastRunLatencyMs: Date.now() - t0 });
    } finally {
      set({ busy: false });
    }
  },

  getTimeline: () => {
    const {
      timelineSource,
      optimisticUserMessage,
      streamingContent,
      lastModel,
      lastRunLatencyMs
    } = get();
    const items = buildTimeline(timelineSource, lastModel);

    if (lastRunLatencyMs != null) {
      for (let i = items.length - 1; i >= 0; i--) {
        if (items[i].role === "assistant") {
          items[i] = { ...items[i], latencyMs: lastRunLatencyMs };
          break;
        }
      }
    }

    if (streamingContent) {
      items.push(syntheticAssistantMessage(streamingContent, lastModel));
    }

    if (optimisticUserMessage) {
      items.push(syntheticUserMessage(optimisticUserMessage));
    }

    return items;
  }
}));
