import { RawJson } from "@/components/ui/Shared";
import { extractDomain } from "@/lib/utils";

interface TavilyResult {
  title?: string;
  url?: string;
  content?: string;
  raw_content?: string;
}

export function TavilySearchRenderer({ data }: { data: Record<string, unknown> }) {
  const results: TavilyResult[] | undefined = Array.isArray(data.results)
    ? (data.results as TavilyResult[])
    : Array.isArray(data.result)
      ? (data.result as TavilyResult[])
      : undefined;

  if (!results || results.length === 0) {
    return <RawJson data={data} />;
  }

  return (
    <div className="mt-2 p-2.5 border border-hairline rounded-lg bg-surface-canvas/40">
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
      <RawJson data={data} />
    </div>
  );
}
