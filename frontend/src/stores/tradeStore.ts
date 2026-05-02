import { create } from "zustand";
import type { SessionTimelineItem, RuntimeEvent } from "@/api";
import type { TimelineItem } from "@/types";
import { api } from "@/api";
import { buildTimeline, humanTime } from "@/lib/utils";

const RUN_TIMEOUT_MS = 120_000;

interface TradeState {
  selectedSessionId: string;
  timelineSource: SessionTimelineItem[];
  events: RuntimeEvent[];
  draft: string;
  busy: boolean;
  loadingTimeline: boolean;

  optimisticUserMessage: string | null;
  streamingContent: string | null;
  streamingReasoning: string | null;
  reasoningStart: number | null;
  lastModel: string | null;
  lastRunLatencyMs: number | null;

  _ws: WebSocket | null;
  _runTimer: ReturnType<typeof setTimeout> | null;
  runError: string | null;

  setSelectedSessionId: (id: string) => void;
  setDraft: (value: string) => void;
  setBusy: (value: boolean) => void;
  setEvents: (events: RuntimeEvent[]) => void;
  pushEvent: (event: RuntimeEvent) => void;

  loadTimeline: (sessionId: string) => Promise<void>;
  sendMessage: (sessionId: string, mode: "run" | "event" | "write", content: string, model?: string | null) => Promise<void>;
  runOnce: (sessionId: string, model?: string | null) => Promise<void>;

  getTimeline: () => TimelineItem[];

  _connectWs: (sessionId: string) => void;
  _disconnectWs: () => void;
}

let _optId = 0;

function syntheticUserMessage(content: string): TimelineItem {
  _optId += 1;
  return {
    id: `opt-${_optId}`,
    kind: "user",
    role: "user",
    time: humanTime(new Date().toISOString()),
    title: "用户",
    body: content
  };
}

function syntheticAssistantMessage(
  content: string,
  model: string | null,
  reasoning?: string | null,
  reasoningDurationMs?: number | null,
): TimelineItem {
  return {
    id: "streaming",
    kind: "assistant",
    role: "assistant",
    time: "",
    title: "助手",
    body: content,
    model,
    streaming: true,
    reasoning: reasoning ?? null,
    reasoningDurationMs: reasoningDurationMs ?? null,
  };
}

export const useTradeStore = create<TradeState>((set, get) => ({
  selectedSessionId: "",
  timelineSource: [],
  events: [],
  draft: "",
  busy: false,
  loadingTimeline: false,

  optimisticUserMessage: null,
  streamingContent: null,
  streamingReasoning: null,
  reasoningStart: null,
  lastModel: null,
  lastRunLatencyMs: null,

  _ws: null,
  _runTimer: null,
  runError: null,

  setSelectedSessionId: (id) =>
    set({
      selectedSessionId: id,
      optimisticUserMessage: null,
      streamingContent: null,
      streamingReasoning: null,
      reasoningStart: null,
      runError: null,
    }),
  setDraft: (value) => set({ draft: value }),
  setBusy: (value) => set({ busy: value }),
  setEvents: (events) => set({ events }),

  pushEvent: (event) =>
    set((s) => ({ events: [event, ...s.events].slice(0, 60) })),

  loadTimeline: async (sessionId) => {
    set({ loadingTimeline: true });
    try {
      const source = await api.sessionTimeline(sessionId);
      set({
        timelineSource: source,
        optimisticUserMessage: null,
        streamingContent: null,
        streamingReasoning: null,
        reasoningStart: null,
        loadingTimeline: false
      });
    } catch {
      set({ loadingTimeline: false });
    }
  },

  _connectWs: (sessionId) => {
    const existing = get()._ws;
    if (existing) {
      existing.close();
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/sessions/${sessionId}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      set({ _ws: ws });
    };

    ws.onmessage = (evt) => {
      let event: RuntimeEvent;
      try {
        event = JSON.parse(evt.data as string) as RuntimeEvent;
      } catch {
        return;
      }
      get().pushEvent(event);

      if (event.type === "assistant_token") {
        set((s) => ({
          streamingContent: (s.streamingContent ?? "") + (event.token ?? ""),
        }));
      }

      if (event.type === "assistant_reasoning") {
        set((s) => ({
          streamingReasoning: (s.streamingReasoning ?? "") + (event.token ?? ""),
          reasoningStart: s.reasoningStart ?? Date.now(),
        }));
      }

      if (event.type === "run_finished") {
        get()._disconnectWs();
        get().loadTimeline(sessionId);
        const t0 = get().lastRunLatencyMs;
        if (t0 != null) {
          set({ lastRunLatencyMs: Date.now() - (Date.now() - t0) });
        }
        set({ busy: false });
      }

      if (event.type === "error") {
        get()._disconnectWs();
        set({ busy: false });
        get().loadTimeline(sessionId);
      }
    };

    ws.onerror = () => {
      get()._disconnectWs();
      set({ busy: false });
    };

    ws.onclose = () => {
      set({ _ws: null });
    };

    set({ _ws: ws });
  },

  _disconnectWs: () => {
    const ws = get()._ws;
    const timer = get()._runTimer;
    if (timer) {
      clearTimeout(timer);
      set({ _runTimer: null });
    }
    if (ws) {
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try { ws.close(); } catch { /* ignore */ }
      set({ _ws: null });
    }
  },

  sendMessage: async (sessionId, mode, content, model) => {
    const t0 = Date.now();
    set({
      draft: "",
      busy: true,
      optimisticUserMessage: content,
      streamingContent: null,
      streamingReasoning: null,
      reasoningStart: null,
      lastModel: model ?? null,
      lastRunLatencyMs: null,
      events: [],
      runError: null,
    });

    if (mode === "write") {
      try {
        await api.createMessage(sessionId, { role: "user", content, message_type: "user" });
        await get().loadTimeline(sessionId);
      } finally {
        set({ busy: false });
      }
      return;
    }

    get()._connectWs(sessionId);

    const timer = setTimeout(() => {
      const state = get();
      if (state.busy) {
        state._disconnectWs();
        set({ busy: false });
        get().loadTimeline(sessionId);
      }
    }, RUN_TIMEOUT_MS);
    set({ _runTimer: timer, lastRunLatencyMs: Date.now() - t0 });

    api.runSession(sessionId, {
      message: mode === "event" ? `[手动事件]\n${content}` : content,
      max_tool_rounds: 5,
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : String(err);
      set({ runError: msg });
      const s = get();
      if (s.busy) {
        s._disconnectWs();
        set({ busy: false });
      }
    });
  },

  runOnce: async (sessionId, model) => {
    set({
      busy: true,
      optimisticUserMessage: null,
      streamingContent: null,
      streamingReasoning: null,
      reasoningStart: null,
      lastModel: model ?? null,
      lastRunLatencyMs: null,
      events: [],
    });

    get()._connectWs(sessionId);

    const timer = setTimeout(() => {
      const state = get();
      if (state.busy) {
        state._disconnectWs();
        set({ busy: false });
        get().loadTimeline(sessionId);
      }
    }, RUN_TIMEOUT_MS);
    set({ _runTimer: timer });

    api.runSession(sessionId, { max_tool_rounds: 5 }).catch((err) => {
      const msg = err instanceof Error ? err.message : String(err);
      set({ runError: msg });
      const s = get();
      if (s.busy) {
        s._disconnectWs();
        set({ busy: false });
      }
    });
  },

  getTimeline: () => {
    const {
      timelineSource,
      optimisticUserMessage,
      streamingContent,
      streamingReasoning,
      reasoningStart,
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
      items.push(syntheticAssistantMessage(
        streamingContent,
        lastModel,
        streamingReasoning,
        null,  // 流式时由组件侧计算耗时，避免 Date.now() 导致无限渲染
      ));
    }

    if (optimisticUserMessage) {
      items.push(syntheticUserMessage(optimisticUserMessage));
    }

    return items;
  }
}));
