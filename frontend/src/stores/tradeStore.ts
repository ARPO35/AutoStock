import { create } from "zustand";
import type { StoreApi } from "zustand";
import type { ReplayClockState, SessionTimelineItem, RuntimeEvent } from "@/api";
import type { TimelineItem } from "@/types";
import { api } from "@/api";
import { buildTimeline, humanTime, syntheticToolCallItem } from "@/lib/utils";
import { useDataStore } from "@/stores/dataStore";

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
  reasoningDurationMs: number | null;
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
  focusedToolCallId: string | null;
  replayClocks: Record<string, ReplayClockState>;
  replayClockLoading: boolean;
  replayClockError: string | null;

  streamedRounds: StreamedRound[];
  currentReasoning: string;
  currentContent: string;
  currentToolCalls: StreamingToolCall[];
  reasoningStartTime: number | null;
  activeReasoningDurationMs: number | null;

  _ws: WebSocket | null;

  setSelectedSessionId: (id: string) => void;
  setDraft: (value: string) => void;
  setBusy: (value: boolean) => void;
  setEvents: (events: RuntimeEvent[]) => void;
  pushEvent: (event: RuntimeEvent) => void;

  loadTimeline: (sessionId: string) => Promise<void>;
  sendMessage: (sessionId: string, content: string, model?: string | null) => Promise<void>;
  runOnce: (sessionId: string, model?: string | null) => Promise<void>;
  stopCurrentRun: (sessionId: string) => Promise<void>;
  focusToolCall: (toolCallId: string | null, sessionId?: string | null) => void;
  loadReplayClock: (accountId: string) => Promise<void>;
  refreshReplayClock: (accountId: string) => Promise<void>;
  updateReplayClock: (accountId: string, payload: Record<string, unknown>) => Promise<ReplayClockState | null>;
  restoreReplayClockLive: (accountId: string) => Promise<ReplayClockState | null>;
  syncReplayClock: (clock: ReplayClockState | null | undefined) => void;

  getTimeline: () => TimelineItem[];

  _connectWs: (sessionId: string) => void;
  _disconnectWs: () => void;
}

let _optId = 0;
let _roundId = 0;
let _streamReasoningBuffer = "";
let _streamContentBuffer = "";
let _streamFlushFrame: number | null = null;
let _streamFlushTimer: number | null = null;

type TradeSet = StoreApi<TradeState>["setState"];

const STREAM_FLUSH_MAX_MS = 50;

function isAssistantStreamEvent(event: RuntimeEvent): boolean {
  return event.type === "assistant_token" || event.type === "assistant_reasoning";
}

function appendStreamTokens(
  set: TradeSet,
  reasoningToken: string,
  contentToken: string,
) {
  if (!reasoningToken && !contentToken) return;

  set((s) => {
    const now = Date.now();
    let streamedRounds = s.streamedRounds;
    let currentReasoning = s.currentReasoning;
    let currentContent = s.currentContent;
    let currentToolCalls = s.currentToolCalls;
    let reasoningStartTime = s.reasoningStartTime;
    let activeReasoningDurationMs = s.activeReasoningDurationMs;

    if (reasoningToken) {
      if (currentToolCalls.length > 0) {
        _roundId += 1;
        streamedRounds = [...streamedRounds, {
          id: `round-${_roundId}`,
          reasoning: currentReasoning,
          content: currentContent,
          toolCalls: currentToolCalls,
          reasoningDurationMs: activeReasoningDurationMs,
        }];
        currentReasoning = reasoningToken;
        currentContent = "";
        currentToolCalls = [];
        reasoningStartTime = now;
        activeReasoningDurationMs = null;
      } else {
        reasoningStartTime = reasoningStartTime ?? (currentReasoning ? null : now);
        currentReasoning += reasoningToken;
      }
    }

    if (contentToken) {
      const reasoningDurationMs =
        activeReasoningDurationMs
        ?? (currentReasoning && reasoningStartTime != null
          ? now - reasoningStartTime
          : null);
      if (currentToolCalls.length > 0) {
        _roundId += 1;
        streamedRounds = [...streamedRounds, {
          id: `round-${_roundId}`,
          reasoning: currentReasoning,
          content: currentContent,
          toolCalls: currentToolCalls,
          reasoningDurationMs,
        }];
        currentReasoning = "";
        currentContent = contentToken;
        currentToolCalls = [];
        reasoningStartTime = null;
        activeReasoningDurationMs = null;
      } else {
        currentContent += contentToken;
        activeReasoningDurationMs = reasoningDurationMs;
        reasoningStartTime = reasoningDurationMs != null ? null : reasoningStartTime;
      }
    }

    return {
      streamedRounds,
      currentReasoning,
      currentContent,
      currentToolCalls,
      reasoningStartTime,
      activeReasoningDurationMs,
    };
  });
}

function cancelScheduledStreamFlush() {
  if (_streamFlushFrame != null) {
    window.cancelAnimationFrame(_streamFlushFrame);
    _streamFlushFrame = null;
  }
  if (_streamFlushTimer != null) {
    window.clearTimeout(_streamFlushTimer);
    _streamFlushTimer = null;
  }
}

function flushStreamBuffer(set: TradeSet) {
  cancelScheduledStreamFlush();
  const reasoningToken = _streamReasoningBuffer;
  const contentToken = _streamContentBuffer;
  _streamReasoningBuffer = "";
  _streamContentBuffer = "";
  appendStreamTokens(set, reasoningToken, contentToken);
}

function scheduleStreamFlush(set: TradeSet) {
  if (_streamFlushFrame == null) {
    _streamFlushFrame = window.requestAnimationFrame(() => {
      flushStreamBuffer(set);
    });
  }
  if (_streamFlushTimer == null) {
    _streamFlushTimer = window.setTimeout(() => {
      flushStreamBuffer(set);
    }, STREAM_FLUSH_MAX_MS);
  }
}

function queueStreamToken(set: TradeSet, event: RuntimeEvent) {
  if (event.type === "assistant_reasoning") {
    _streamReasoningBuffer += event.token ?? "";
  }
  if (event.type === "assistant_token") {
    _streamContentBuffer += event.token ?? "";
  }
  scheduleStreamFlush(set);
}

function resetStreamBuffer() {
  cancelScheduledStreamFlush();
  _streamReasoningBuffer = "";
  _streamContentBuffer = "";
}

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
  focusedToolCallId: null,
  replayClocks: {},
  replayClockLoading: false,
  replayClockError: null,

  streamedRounds: [],
  currentReasoning: "",
  currentContent: "",
  currentToolCalls: [],
  reasoningStartTime: null,
  activeReasoningDurationMs: null,

  _ws: null,

  setSelectedSessionId: (id) =>
    set({
      selectedSessionId: id,
      optimisticUserMessage: null,
      streamedRounds: [],
      currentReasoning: "",
      currentContent: "",
      currentToolCalls: [],
      reasoningStartTime: null,
      activeReasoningDurationMs: null,
      runError: null,
      runNotice: null,
      focusedToolCallId: null,
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
        reasoningStartTime: null,
        activeReasoningDurationMs: null,
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
      if (isAssistantStreamEvent(event)) {
        queueStreamToken(set, event);
        return;
      }

      flushStreamBuffer(set);
      get().pushEvent(event);

      if (event.type === "run_started" && event.clock?.account_id) {
        get().syncReplayClock(event.clock);
      }

      if (event.type === "tool_call_started") {
        set((s) => {
          const now = Date.now();
          const reasoningDurationMs =
            s.activeReasoningDurationMs
            ?? (s.currentReasoning && s.reasoningStartTime != null
              ? now - s.reasoningStartTime
              : null);

          return {
            currentToolCalls: [...s.currentToolCalls, {
              toolCallId: event.tool_call_id ?? "",
              toolName: event.tool_name ?? "",
              arguments_json: event.arguments_json ?? "{}",
              status: "running",
              rawResult: null,
            }],
            activeReasoningDurationMs: reasoningDurationMs,
            reasoningStartTime: reasoningDurationMs != null ? null : s.reasoningStartTime,
          };
        });
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
          const now = Date.now();
          const reasoningDurationMs =
            s.activeReasoningDurationMs
            ?? (s.currentReasoning && s.reasoningStartTime != null
              ? now - s.reasoningStartTime
              : null);
          if (!s.currentReasoning && !s.currentContent && s.currentToolCalls.length === 0) {
            return {
              runNotice: cancelled ? "已停止当前运行" : s.runNotice,
              reasoningStartTime: null,
              activeReasoningDurationMs: null,
            };
          }
          _roundId += 1;
          return {
            streamedRounds: [...s.streamedRounds, {
              id: `round-${_roundId}`,
              reasoning: s.currentReasoning,
              content: s.currentContent,
              toolCalls: s.currentToolCalls,
              reasoningDurationMs,
            }],
            currentReasoning: "",
            currentContent: "",
            currentToolCalls: [],
            reasoningStartTime: null,
            activeReasoningDurationMs: null,
            runNotice: cancelled ? "已停止当前运行" : s.runNotice,
          };
        });
        get()._disconnectWs();
        void useDataStore.getState().loadSessions();
        get().loadTimeline(sessionId);
      }

      if (event.type === "error") {
        get()._disconnectWs();
        set({ busy: false, runError: event.error ?? "运行失败" });
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
    flushStreamBuffer(set);
    const ws = get()._ws;
    if (ws) {
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try { ws.close(); } catch { /* ignore */ }
      set({ _ws: null });
    }
  },

  sendMessage: async (sessionId, content, model) => {
    resetStreamBuffer();
    set({
      draft: "",
      busy: true,
      optimisticUserMessage: content,
      streamedRounds: [],
      currentReasoning: "",
      currentContent: "",
      currentToolCalls: [],
      reasoningStartTime: null,
      activeReasoningDurationMs: null,
      lastModel: model ?? null,
      lastRunLatencyMs: null,
      events: [],
      runError: null,
      runNotice: null,
    });

    get()._connectWs(sessionId);

    api.runSession(sessionId, {
      message: content,
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
    resetStreamBuffer();
    set({
      busy: true,
      optimisticUserMessage: null,
      streamedRounds: [],
      currentReasoning: "",
      currentContent: "",
      currentToolCalls: [],
      reasoningStartTime: null,
      activeReasoningDurationMs: null,
      lastModel: model ?? null,
      lastRunLatencyMs: null,
      events: [],
      runError: null,
      runNotice: null,
    });

    get()._connectWs(sessionId);

    api.runSession(sessionId, {}).catch((err) => {
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

  focusToolCall: (toolCallId, sessionId) => {
    if (sessionId && sessionId !== get().selectedSessionId) {
      set({ selectedSessionId: sessionId, focusedToolCallId: toolCallId });
      return;
    }
    set({ focusedToolCallId: toolCallId });
  },

  loadReplayClock: async (accountId) => {
    if (!accountId) return;
    set({ replayClockLoading: true, replayClockError: null });
    try {
      const clock = await api.replayClock(accountId);
      set((s) => ({
        replayClocks: { ...s.replayClocks, [accountId]: clock },
        replayClockLoading: false,
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ replayClockLoading: false, replayClockError: msg });
    }
  },

  refreshReplayClock: async (accountId) => {
    if (!accountId) return;
    try {
      const clock = await api.replayClock(accountId);
      set((s) => ({
        replayClocks: { ...s.replayClocks, [accountId]: clock },
        replayClockError: null,
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ replayClockError: msg });
    }
  },

  updateReplayClock: async (accountId, payload) => {
    if (!accountId) return null;
    set({ replayClockLoading: true, replayClockError: null });
    try {
      const clock = await api.updateReplayClock(accountId, payload);
      set((s) => ({
        replayClocks: { ...s.replayClocks, [accountId]: clock },
        replayClockLoading: false,
      }));
      return clock;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ replayClockLoading: false, replayClockError: msg });
      return null;
    }
  },

  restoreReplayClockLive: async (accountId) => {
    if (!accountId) return null;
    set({ replayClockLoading: true, replayClockError: null });
    try {
      const clock = await api.restoreReplayClockLive(accountId);
      set((s) => ({
        replayClocks: { ...s.replayClocks, [accountId]: clock },
        replayClockLoading: false,
      }));
      return clock;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ replayClockLoading: false, replayClockError: msg });
      return null;
    }
  },

  syncReplayClock: (clock) => {
    if (!clock?.account_id) return;
    set((s) => ({
      replayClocks: { ...s.replayClocks, [clock.account_id]: clock },
      replayClockError: null,
    }));
  },

  getTimeline: () => {
    const {
      timelineSource,
      optimisticUserMessage,
      streamedRounds,
      currentReasoning,
      currentContent,
      currentToolCalls,
      reasoningStartTime,
      activeReasoningDurationMs,
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
          round.reasoningDurationMs,
          round.id,
        ));
      }
      for (const tc of round.toolCalls) {
        items.push(syntheticToolCallItem(tc));
      }
    }

    if (currentReasoning || currentContent) {
      const currentReasoningDurationMs = activeReasoningDurationMs
        ?? (currentReasoning && reasoningStartTime != null
          ? Date.now() - reasoningStartTime
          : null);
      items.push(syntheticAssistantMessage(
        currentContent,
        lastModel,
        currentReasoning || null,
        currentReasoningDurationMs,
        "current",
      ));
    }
    for (const tc of currentToolCalls) {
      items.push(syntheticToolCallItem(tc));
    }

    return items;
  }
}));
