import { type KeyboardEvent, useCallback, useState } from "react";
import { Pause, Play, Settings } from "lucide-react";
import { useTradeStore } from "@/stores/tradeStore";
import { useDataStore } from "@/stores/dataStore";
import { TradeConfigPopover } from "@/features/trade/TradeConfigPopover";

export function ChatInputBox() {
  const draft = useTradeStore((s) => s.draft);
  const setDraft = useTradeStore((s) => s.setDraft);
  const busy = useTradeStore((s) => s.busy);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const sendMessage = useTradeStore((s) => s.sendMessage);
  const stopCurrentRun = useTradeStore((s) => s.stopCurrentRun);
  const runError = useTradeStore((s) => s.runError);
  const runNotice = useTradeStore((s) => s.runNotice);
  const [focused, setFocused] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);

  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const hasProvider = selectedSession?.provider_id && providers.some((p) => p.id === selectedSession.provider_id);

  const noProvider = !!selectedSessionId && !hasProvider;
  const disabled = !selectedSessionId || noProvider;
  const canSend = !busy && !disabled && draft.trim().length > 0;

  const sendRun = useCallback(() => {
    if (!canSend) return;
    sendMessage(selectedSessionId, "run", draft.trim(), selectedSession?.model);
  }, [canSend, draft, selectedSessionId, selectedSession?.model, sendMessage]);

  const handlePrimaryAction = useCallback(() => {
    if (busy) {
      if (selectedSessionId) void stopCurrentRun(selectedSessionId);
      return;
    }
    sendRun();
  }, [busy, selectedSessionId, sendRun, stopCurrentRun]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendRun();
      }
    },
    [sendRun]
  );

  return (
    <footer className="pointer-events-none relative z-20 flex-shrink-0 bg-gradient-to-t from-surface-canvas via-surface-canvas/95 to-surface-canvas/0 px-4 pb-4 pt-3">
      <div className="pointer-events-auto mx-auto w-full max-w-[960px]">
        <div
          className={`relative grid grid-cols-[minmax(0,1fr)_44px_44px] items-end gap-2 border bg-surface-card/95 p-1.5 shadow-2xl transition-all duration-300 ease-out ${
            focused
              ? "rounded-xl border-brand-primary/60"
              : "rounded-pill border-hairline"
          }`}
        >
          <textarea
            rows={1}
            className={`block w-full resize-none bg-transparent px-4 text-sm leading-relaxed text-text-on-dark placeholder:text-text-muted transition-all duration-300 ease-out disabled:opacity-50 ${
              focused ? "min-h-[96px] py-2.5" : "min-h-[42px] py-2.5"
            }`}
            value={draft}
            disabled={disabled}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder={
              noProvider
                ? "请先为当前 Session 选择 Provider。"
                : disabled
                  ? "请先创建并选择 Session。"
                  : "输入给 LLM 的问题。Shift + Enter 换行，Enter 发送。"
            }
          />

          <button
            className={`grid h-11 w-11 place-items-center rounded-full transition-colors ${
              busy
                ? "border border-trading-rise/50 bg-trading-rise/10 text-trading-rise hover:bg-trading-rise/15"
                : "bg-brand-primary text-brand-ink hover:bg-brand-primary-active"
            } disabled:opacity-50`}
            type="button"
            disabled={busy ? !selectedSessionId : !canSend}
            onClick={handlePrimaryAction}
            title={busy ? "停止当前运行" : "发送"}
          >
            {busy ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
          </button>

          <div className="relative">
            <button
              className={`grid h-11 w-11 place-items-center rounded-full border transition-colors ${
                configOpen
                  ? "border-brand-primary/70 bg-brand-primary/10 text-brand-primary"
                  : "border-hairline bg-surface-canvas text-text-muted hover:border-brand-primary/60 hover:text-brand-primary"
              }`}
              type="button"
              onClick={() => setConfigOpen((value) => !value)}
              title="配置"
            >
              <Settings size={18} />
            </button>
            <TradeConfigPopover open={configOpen} onClose={() => setConfigOpen(false)} />
          </div>
        </div>

        {runError && (
          <p className="mt-2 px-4 text-xs text-trading-rise">{runError}</p>
        )}
        {!runError && runNotice && (
          <p className="mt-2 px-4 text-xs text-text-muted">{runNotice}</p>
        )}
      </div>
    </footer>
  );
}
