import { RawJson } from "@/components/ui/Shared";
import { extractDomain } from "@/lib/utils";

interface TavilyResult {
  title?: string;
  url?: string;
  content?: string;
  raw_content?: string;
  published_date?: string;
  score?: number;
  error?: string;
}

export function TavilySearchRenderer({ data }: { data: Record<string, unknown> }) {
  const results: TavilyResult[] | undefined = Array.isArray(data.results)
    ? (data.results as TavilyResult[])
    : Array.isArray(data.result)
      ? (data.result as TavilyResult[])
      : undefined;
  const failedResults: TavilyResult[] = Array.isArray(data.failed_results)
    ? (data.failed_results as TavilyResult[])
    : [];

  if (!results || results.length === 0) {
    return <RawJson data={data} />;
  }

  return (
    <div className="mt-2 p-2.5 border border-hairline rounded-lg bg-surface-canvas/40">
      <div className="mb-2 flex flex-wrap gap-2 text-[11px] text-text-muted">
        {typeof data.operation === "string" && <span>{data.operation}</span>}
        {typeof data.cache_hit === "boolean" && <span>{data.cache_hit ? "缓存命中" : "实时请求"}</span>}
        {typeof data.credits_estimated === "number" && <span>{data.credits_estimated} credit</span>}
        {typeof data.latency_ms === "number" && <span>{data.latency_ms}ms</span>}
      </div>
      <ol className="grid gap-2 list-decimal pl-5 m-0">
        {results.map((result, i) => (
          <li key={i}>
            <details className="cursor-pointer">
              <summary className="list-none">
                <span className="block text-text-on-dark text-sm">
                  {result.title ?? `结果 ${i + 1}`}
                </span>
                <small className="block text-brand-primary text-xs mt-0.5">
                  {result.url ? extractDomain(result.url) : "无域名"}
                  {result.published_date ? ` · ${result.published_date}` : ""}
                  {typeof result.score === "number" ? ` · ${result.score.toFixed(2)}` : ""}
                </small>
              </summary>
              <div className="mt-2 p-2.5 rounded-lg bg-surface-canvas text-text-body text-xs leading-relaxed">
                {result.url && (
                  <p className="mb-1 text-text-muted break-all">
                    <a
                      className="text-brand-primary hover:underline"
                      href={result.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {result.url}
                    </a>
                  </p>
                )}
                <p className="m-0">
                  {result.content ?? result.raw_content ?? "无内容片段"}
                </p>
              </div>
            </details>
          </li>
        ))}
      </ol>
      {failedResults.length > 0 && (
        <div className="mt-2 rounded-lg border border-trading-rise/30 bg-trading-rise/10 p-2 text-xs text-trading-rise">
          {failedResults.map((item, index) => (
            <p key={index} className="m-0 break-all">
              {item.url ?? `失败 ${index + 1}`}：{item.error ?? "抽取失败"}
            </p>
          ))}
        </div>
      )}
      <RawJson data={data} />
    </div>
  );
}
