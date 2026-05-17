import { type KeyboardEvent, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Pause, Play, Settings } from "lucide-react";
import { useTradeStore } from "@/stores/tradeStore";
import { useDataStore } from "@/stores/dataStore";
import { TradeConfigPopover } from "@/features/trade/TradeConfigPopover";
import { resolveModelSelection } from "@/lib/providerModels";

type ChatInputBoxProps = {
  onSafeAreaChange?: (safeAreaPx: number) => void;
};

export function ChatInputBox({ onSafeAreaChange }: ChatInputBoxProps) {
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
  const footerRef = useRef<HTMLElement>(null);
  const inputSurfaceRef = useRef<HTMLDivElement>(null);

  const sessions = useDataStore((s) => s.sessions);
  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const providers = useDataStore((s) => s.providers);
  const hasModelSelection = !!selectedSession && !!resolveModelSelection(providers, selectedSession.model, selectedSession.provider_id);
  const disabled = !selectedSessionId || !hasModelSelection;
  const canSend = !busy && !disabled && draft.trim().length > 0;

  const sendRun = useCallback(() => {
    if (!canSend) return;
    void sendMessage(selectedSessionId, draft.trim(), selectedSession?.model);
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

  const reportSafeArea = useCallback(() => {
    const footer = footerRef.current;
    const inputSurface = inputSurfaceRef.current;
    const host = footer?.offsetParent;
    if (!footer || !inputSurface || !(host instanceof HTMLElement)) return;

    const hostRect = host.getBoundingClientRect();
    const inputRect = inputSurface.getBoundingClientRect();
    const safeAreaPx = Math.max(0, Math.ceil(hostRect.bottom - inputRect.top));
    onSafeAreaChange?.(safeAreaPx);
  }, [onSafeAreaChange]);

  useLayoutEffect(() => {
    reportSafeArea();
  }, [focused, runError, runNotice, reportSafeArea]);

  useEffect(() => {
    const footer = footerRef.current;
    const inputSurface = inputSurfaceRef.current;
    if (!footer || !inputSurface) return;

    const observer = new ResizeObserver(reportSafeArea);
    observer.observe(footer);
    observer.observe(inputSurface);
    window.addEventListener("resize", reportSafeArea);
    reportSafeArea();

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", reportSafeArea);
    };
  }, [reportSafeArea]);

  return (
    <footer ref={footerRef} className="pointer-events-none absolute inset-x-0 bottom-0 z-20 px-4 pb-4 pt-5">
      <div className="pointer-events-auto mx-auto w-full min-w-0 max-w-[860px] sm:w-[72%] sm:min-w-[360px]">
        <div
          ref={inputSurfaceRef}
          data-testid="chat-input-surface"
          className={`relative border bg-surface-card/95 p-1.5 shadow-2xl transition-all duration-300 ease-out ${
            focused
              ? "rounded-xl border-brand-primary/60"
              : "rounded-3xl border-hairline"
          }`}
        >
          <textarea
            rows={1}
            className={`block w-full resize-none bg-transparent text-sm leading-relaxed text-text-on-dark placeholder:text-text-muted transition-all duration-300 ease-out disabled:opacity-50 ${
              focused
                ? "min-h-[96px] py-2.5 px-4"
                : "min-h-[42px] overflow-y-hidden py-2.5 pr-[108px] pl-4"
            }`}
            value={draft}
            disabled={disabled}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder={
              !selectedSessionId
                ? "请先创建并选择 Session。"
                : !hasModelSelection
                  ? "请先为当前 Session 选择模型。"
                  : disabled
                    ? "请先创建并选择 Session。"
                    : "输入给 LLM 的问题。Shift + Enter 换行，Enter 发送。"
            }
          />

          <div
            className={`absolute top-1/2 -translate-y-1/2 flex items-center transition-all duration-300 ease-out ${
              focused
                ? "right-[-56px] flex-col gap-2"
                : "right-2 flex-row gap-1"
            }`}
          >
            <div className="relative order-1">
              <button
                className={`grid h-11 w-11 place-items-center rounded-full border transition-colors ${
                  configOpen
                    ? "border-brand-primary/70 bg-brand-primary/10 text-brand-primary"
                    : "border-hairline bg-surface-canvas text-text-muted hover:border-brand-primary/60 hover:text-brand-primary"
                }`}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setConfigOpen((value) => !value)}
                title="配置"
              >
                <Settings size={18} />
              </button>
              <TradeConfigPopover open={configOpen} onClose={() => setConfigOpen(false)} />
            </div>

            <button
              className={`order-2 grid h-11 w-11 place-items-center rounded-full transition-colors ${
                busy
                  ? "border border-trading-rise/50 bg-trading-rise/10 text-trading-rise hover:bg-trading-rise/15"
                  : "bg-brand-primary text-brand-ink hover:bg-brand-primary-active"
              } disabled:opacity-50`}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              disabled={busy ? !selectedSessionId : !canSend}
              onClick={handlePrimaryAction}
              title={busy ? "停止当前运行" : "发送"}
            >
              {busy ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
            </button>
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
