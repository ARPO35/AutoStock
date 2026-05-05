import { type KeyboardEvent, useCallback } from "react";
import { Send, StopCircle } from "lucide-react";
import { useTradeStore } from "@/stores/tradeStore";
import { useDataStore } from "@/stores/dataStore";

export function ChatInputBox() {
  const draft = useTradeStore((s) => s.draft);
  const setDraft = useTradeStore((s) => s.setDraft);
  const busy = useTradeStore((s) => s.busy);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const sendMessage = useTradeStore((s) => s.sendMessage);
  const stopCurrentRun = useTradeStore((s) => s.stopCurrentRun);
  const runError = useTradeStore((s) => s.runError);
  const runNotice = useTradeStore((s) => s.runNotice);

  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const hasProvider = selectedSession?.provider_id && providers.some((p) => p.id === selectedSession.provider_id);

  const noProvider = !!selectedSessionId && !hasProvider;
  const disabled = !selectedSessionId || noProvider;
  const canSend = !busy && !disabled && draft.trim().length > 0;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (canSend) sendMessage(selectedSessionId, "run", draft.trim(), selectedSession?.model);
      }
    },
    [canSend, draft, selectedSessionId, selectedSession?.model, sendMessage]
  );

  return (
    <footer className="border-t border-hairline p-3 bg-surface-canvas/50 flex-shrink-0">
      <div className="grid grid-cols-[minmax(0,1fr)_132px] gap-2.5">
        <textarea
          className="w-full min-h-[78px] resize-y px-3 py-2.5 rounded-lg bg-surface-card border border-hairline text-text-on-dark placeholder:text-text-muted focus:border-accent-turquoise focus:ring-2 focus:ring-accent-turquoise/50 leading-relaxed text-sm"
          value={draft}
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            noProvider
              ? "请先在顶部为当前 Session 选择 Provider 和模型。"
              : disabled
                ? "请先创建并选择 Session。"
                : "输入给 LLM 的问题。Shift + Enter 换行，Enter 发送。"
          }
        />
        <div className="flex flex-col gap-1.5">
          <button
            className="inline-flex items-center justify-center gap-1.5 h-9 px-3 rounded-md bg-brand-primary text-brand-ink font-semibold text-sm hover:bg-brand-primary-active disabled:opacity-50 transition-colors"
            type="button"
            disabled={!canSend}
            onClick={() => sendMessage(selectedSessionId, "run", draft.trim(), selectedSession?.model)}
          >
            <Send size={17} />
            发送
          </button>
          <button
            className="inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg border border-hairline bg-surface-card text-text-body text-sm hover:bg-surface-elevated disabled:opacity-50 transition-colors"
            type="button"
            disabled={!canSend}
            onClick={() => sendMessage(selectedSessionId, "event", draft.trim(), selectedSession?.model)}
          >
            作为事件运行
          </button>
          <button
            className="inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg border border-hairline bg-surface-card text-text-body text-sm hover:bg-surface-elevated disabled:opacity-50 transition-colors"
            type="button"
            disabled={!canSend}
            onClick={() => sendMessage(selectedSessionId, "write", draft.trim(), selectedSession?.model)}
          >
            只写入
          </button>
          <button
            className="inline-flex items-center justify-center gap-1.5 h-9 px-3 rounded-lg border border-trading-rise/50 bg-trading-rise/10 text-trading-rise text-sm disabled:opacity-50 transition-colors"
            type="button"
            disabled={!busy || !selectedSessionId}
            onClick={() => selectedSessionId && stopCurrentRun(selectedSessionId)}
            title={busy ? "停止当前运行" : "当前没有正在运行的任务"}
          >
            <StopCircle size={15} />
            停止
          </button>
        </div>
      </div>
      {runError && (
        <p className="mt-2 text-trading-rise text-xs">{runError}</p>
      )}
      {!runError && runNotice && (
        <p className="mt-2 text-text-muted text-xs">{runNotice}</p>
      )}
    </footer>
  );
}
