import { create } from "zustand";
import type { SessionTimelineItem, RuntimeEvent } from "@/api";
import type { TimelineItem } from "@/types";
import { api } from "@/api";
import { buildTimeline, humanTime, syntheticToolCallItem } from "@/lib/utils";
import { useDataStore } from "@/stores/dataStore";

const RUN_TIMEOUT_MS = 120_000;

export interface StreamingToolCall {
  toolCallId: string;
  toolName: string;
  arguments_json: string;
  status: string;
  error?: string | null;
  rawResult: Record<string, unknown> | null;
}

interface StreamedRound {
  id: string;
  reasoning: string;
  content: string;
  toolCalls: StreamingToolCall[];
}

interface TradeState {
  selectedSessionId: string;
  timelineSource: SessionTimelineItem[];
  events: RuntimeEvent[];
  draft: string;
  busy: boolean;
  loadingTimeline: boolean;

  optimisticUserMessage: string | null;
  lastModel: string | null;
  lastRunLatencyMs: number | null;
  runError: string | null;
  runNotice: string | null;

  streamedRounds: StreamedRound[];
  currentReasoning: string;
  currentContent: string;
  currentToolCalls: StreamingToolCall[];

  _ws: WebSocket | null;
  _runTimer: ReturnType<typeof setTimeout> | null;

  setSelectedSessionId: (id: string) => void;
  setDraft: (value: string) => void;
  setBusy: (value: boolean) => void;
  setEvents: (events: RuntimeEvent[]) => void;
  pushEvent: (event: RuntimeEvent) => void;

  loadTimeline: (sessionId: string) => Promise<void>;
  sendMessage: (sessionId: string, mode: "run" | "event" | "write", content: string, model?: string | null) => Promise<void>;
  runOnce: (sessionId: string, model?: string | null) => Promise<void>;
  stopCurrentRun: (sessionId: string) => Promise<void>;

  getTimeline: () => TimelineItem[];

  _connectWs: (sessionId: string) => void;
  _disconnectWs: () => void;
}

let _optId = 0;
let _roundId = 0;

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
  roundId?: string,
): TimelineItem {
  return {
    id: roundId ?? "streaming-current",
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
  lastModel: null,
  lastRunLatencyMs: null,
  runError: null,
  runNotice: null,

  streamedRounds: [],
  currentReasoning: "",
  currentContent: "",
  currentToolCalls: [],

  _ws: null,
  _runTimer: null,

  setSelectedSessionId: (id) =>
    set({
      selectedSessionId: id,
      optimisticUserMessage: null,
      streamedRounds: [],
      currentReasoning: "",
        currentContent: "",
        currentToolCalls: [],
        runError: null,
        runNotice: null,
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
        streamedRounds: [],
        currentReasoning: "",
        currentContent: "",
        currentToolCalls: [],
        loadingTimeline: false,
        busy: false,
        runNotice: null,
      });
    } catch {
      set({ loadingTimeline: false, busy: false });
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

      if (event.type === "assistant_reasoning") {
        set((s) => {
          if (s.currentToolCalls.length > 0) {
            _roundId += 1;
            return {
              streamedRounds: [...s.streamedRounds, {
                id: `round-${_roundId}`,
                reasoning: s.currentReasoning,
                content: s.currentContent,
                toolCalls: s.currentToolCalls,
              }],
              currentReasoning: event.token ?? "",
              currentContent: "",
              currentToolCalls: [],
            };
          }
          return { currentReasoning: s.currentReasoning + (event.token ?? "") };
        });
      }

      if (event.type === "assistant_token") {
        set((s) => {
          if (s.currentToolCalls.length > 0) {
            _roundId += 1;
            return {
              streamedRounds: [...s.streamedRounds, {
                id: `round-${_roundId}`,
                reasoning: s.currentReasoning,
                content: s.currentContent,
                toolCalls: s.currentToolCalls,
              }],
              currentReasoning: "",
              currentContent: event.token ?? "",
              currentToolCalls: [],
            };
          }
          return { currentContent: s.currentContent + (event.token ?? "") };
        });
      }

      if (event.type === "tool_call_started") {
        set((s) => ({
          currentToolCalls: [...s.currentToolCalls, {
            toolCallId: event.tool_call_id ?? "",
            toolName: event.tool_name ?? "",
            arguments_json: event.arguments_json ?? "{}",
            status: "running",
            rawResult: null,
          }],
        }));
      }

      if (event.type === "tool_call_finished") {
        set((s) => ({
          currentToolCalls: s.currentToolCalls.map((tc) =>
            tc.toolCallId === event.tool_call_id
              ? {
                  ...tc,
                  status: event.ok ? "finished" : "error",
                  error: event.error ?? tc.error,
                  rawResult: (event.result as Record<string, unknown>) ?? null,
                }
              : tc
          ),
        }));
      }

      if (event.type === "run_finished") {
        const cancelled = String(event.status ?? "").toLowerCase().includes("cancel");
        set((s) => {
          if (!s.currentReasoning && !s.currentContent && s.currentToolCalls.length === 0) {
            return { runNotice: cancelled ? "已停止当前运行" : s.runNotice };
          }
          _roundId += 1;
          return {
            streamedRounds: [...s.streamedRounds, {
              id: `round-${_roundId}`,
              reasoning: s.currentReasoning,
              content: s.currentContent,
              toolCalls: s.currentToolCalls,
            }],
            currentReasoning: "",
            currentContent: "",
            currentToolCalls: [],
            runNotice: cancelled ? "已停止当前运行" : s.runNotice,
          };
        });
        get()._disconnectWs();
        void useDataStore.getState().loadSessions();
        get().loadTimeline(sessionId);
      }

      if (event.type === "error") {
        get()._disconnectWs();
        set({ busy: false });
        void useDataStore.getState().loadSessions();
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
    set({
      draft: "",
      busy: true,
      optimisticUserMessage: content,
      streamedRounds: [],
      currentReasoning: "",
      currentContent: "",
      currentToolCalls: [],
      lastModel: model ?? null,
      lastRunLatencyMs: null,
      events: [],
      runError: null,
      runNotice: null,
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
      const s = get();
      if (s.busy) {
        s._disconnectWs();
        set({ busy: false });
        get().loadTimeline(sessionId);
      }
    }, RUN_TIMEOUT_MS);
    set({ _runTimer: timer });

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
      streamedRounds: [],
      currentReasoning: "",
      currentContent: "",
      currentToolCalls: [],
      lastModel: model ?? null,
      lastRunLatencyMs: null,
      events: [],
      runError: null,
      runNotice: null,
    });

    get()._connectWs(sessionId);

    const timer = setTimeout(() => {
      const s = get();
      if (s.busy) {
        s._disconnectWs();
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

  stopCurrentRun: async (sessionId) => {
    try {
      const result = await api.stopSession(sessionId);
      set({ runNotice: result.status === "cancelled" ? "已停止当前运行" : "当前没有正在运行的任务" });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ runNotice: `停止请求失败：${msg}` });
    } finally {
      get()._disconnectWs();
      set({ busy: false });
      await get().loadTimeline(sessionId);
    }
  },

  getTimeline: () => {
    const {
      timelineSource,
      optimisticUserMessage,
      streamedRounds,
      currentReasoning,
      currentContent,
      currentToolCalls,
      lastModel,
      lastRunLatencyMs,
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

    if (optimisticUserMessage) {
      items.push(syntheticUserMessage(optimisticUserMessage));
    }

    for (const round of streamedRounds) {
      if (round.reasoning || round.content) {
        items.push(syntheticAssistantMessage(
          round.content,
          lastModel,
          round.reasoning || null,
          null,
          round.id,
        ));
      }
      for (const tc of round.toolCalls) {
        items.push(syntheticToolCallItem(tc));
      }
    }

    if (currentReasoning || currentContent) {
      items.push(syntheticAssistantMessage(
        currentContent,
        lastModel,
        currentReasoning || null,
        null,
        "current",
      ));
    }
    for (const tc of currentToolCalls) {
      items.push(syntheticToolCallItem(tc));
    }

    return items;
  }
}));
