import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  RefreshCw,
  KeyRound,
  Bot,
  Wrench,
  Bell,
  Database,
  Settings,
  Code2,
  CheckCircle2,
  AlertTriangle,
  Plus,
  Trash2,
  Plug,
  Zap,
  Search,
  BarChart3
} from "lucide-react";
import type { ToolSchema, DataConflict, CacheStatusRow, ProviderModelsResponse, ProviderChatTestResponse, ProviderUsageResponse, TavilyConfig, TavilyUsageResponse, TavilyTestResponse, UsageSummaryResponse, UsageRunRow, UsageGroupRow } from "@/api";
import { api } from "@/api";
import { useDataStore } from "@/stores/dataStore";
import { useMarketStore } from "@/stores/marketStore";
import { useUIStore, manageSections } from "@/stores/uiStore";
import { PromptManagement } from "@/pages/manage/PromptManagement";
import {
  EmptyState,
  PanelHeader,
  InfoGrid,
  RawJson,
  SubTabs
} from "@/components/ui/Shared";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea } from "@/components/ui/Input";
import {
  humanTime,
  conflictSummary,
  parseInputObject
} from "@/lib/utils";
import { providerModelOptions, resolveProviderByModelValue } from "@/lib/providerModels";

/* ------------------------------------------------------------------ */
/*  Page shell                                                        */
/* ------------------------------------------------------------------ */

export function ManagePage() {
  const manageSection = useUIStore((s) => s.manageSection);
  const setManageSection = useUIStore((s) => s.setManageSection);
  const selectedTool = useUIStore((s) => s.selectedTool);
  const setSelectedTool = useUIStore((s) => s.setSelectedTool);
  const tools = useDataStore((s) => s.tools);
  const refreshAll = useDataStore((s) => s.refreshAll);

  return (
    <section className="flex flex-col min-h-0 gap-3 p-4">
      <PageHeader
        eyebrow={`管理中心 - ${manageSection}`}
        title="管理 LLM 提供商、API 配置、Skills、Tools、触发器与数据源"
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              icon={<KeyRound size={14} />}
              disabled
            >
              使用指南
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<RefreshCw size={14} />}
              onClick={() => void refreshAll()}
            >
              刷新
            </Button>
          </>
        }
      />

      <div
        className={`grid gap-3 min-h-0 flex-1 overflow-hidden ${
          manageSection === "Tools"
            ? "grid-cols-[190px_1fr_1fr]"
            : "grid-cols-[190px_1fr]"
        }`}
      >
        {/* Left Sidebar */}
        <aside className="border border-hairline rounded-xl bg-surface-card p-2 min-h-0 overflow-auto">
          {manageSections.map((section) => (
            <button
              key={section}
              type="button"
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors text-left ${
                manageSection === section
                  ? "text-text-on-dark bg-surface-elevated shadow-[inset_0_-2px_0_#fcd535]"
                  : "text-text-muted hover:text-text-on-dark hover:bg-surface-elevated"
              }`}
              onClick={() => setManageSection(section)}
            >
              {sectionIcon(section)}
              <span>{section}</span>
            </button>
          ))}
        </aside>

        {/* Main Content */}
        <section className="border border-hairline rounded-xl bg-surface-card p-4 min-h-0 overflow-auto">
          {manageSection === "模型与API" && <ProviderManagement />}
          {manageSection === "提示词" && <PromptManagement />}
          {manageSection === "Tavily" && <TavilyManagement />}
          {manageSection === "用量分析" && <UsageManagement />}
          {manageSection === "Tools" && <ToolManagement />}
          {manageSection === "数据管理" && <DataManagement />}
          {manageSection === "Skills" && <SkillsPlaceholder />}
          {manageSection === "触发器" && <TriggersPlaceholder />}
          {manageSection === "系统设置" && <SystemSettings />}
        </section>

        {/* Right Tool Catalog — only visible when Tools section is active */}
        {manageSection === "Tools" && (
          <aside className="border border-hairline rounded-xl bg-surface-card p-3 min-h-0 overflow-auto">
            <PanelHeader icon={<Wrench size={16} />} title="Tools（工具目录）" />
            {tools.length === 0 ? (
              <EmptyState
                title="暂无工具"
                description="后端 /api/tools 未返回工具。"
              />
            ) : (
              <div className="grid gap-1 mt-2">
                {tools.map((tool) => (
                  <div
                    key={tool.name}
                    className="px-3 py-2 rounded-lg border border-hairline bg-surface-canvas/50 text-sm cursor-pointer hover:border-brand-primary/30 hover:bg-brand-primary/5 transition-colors"
                    onClick={() => {
                      setManageSection("Tools");
                      setSelectedTool(tool.name);
                    }}
                  >
                    <strong className="block text-text-on-dark text-xs">
                      {tool.display_name || tool.name}
                    </strong>
                    <small className="text-text-muted text-xs truncate block">
                      {tool.description}
                    </small>
                  </div>
                ))}
              </div>
            )}
          </aside>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  PageHeader                                                        */
/* ------------------------------------------------------------------ */

function PageHeader({
  eyebrow,
  title,
  actions
}: {
  eyebrow: string;
  title: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex items-center justify-between gap-3.5 flex-shrink-0">
      <div className="min-w-0">
        <p className="text-brand-primary text-xs font-bold tracking-wide mb-1">
          {eyebrow}
        </p>
        <h1 className="text-lg font-semibold text-text-on-dark truncate">
          {title}
        </h1>
      </div>
      {actions && (
        <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>
      )}
    </header>
  );
}

/* ------------------------------------------------------------------ */
/*  ProviderManagement                                                */
/* ------------------------------------------------------------------ */

const defaultProviderForm: {
  provider_type: string;
  name: string;
  base_url: string;
  api_key: string;
  supports_tools: boolean;
  supports_strict_schema: boolean;
  strict_tool_schema: boolean;
} = {
  provider_type: "",
  name: "",
  base_url: "",
  api_key: "",
  supports_tools: true,
  supports_strict_schema: false,
  strict_tool_schema: false
};

function providerTypeLabel(type: string): string {
  if (type === "deepseek") return "DeepSeek";
  if (type === "openai_compatible") return "OpenAI-Compatible";
  return type || "--";
}

const providerModelsCacheKey = (providerId: string) => `autostock.providerConnectModels.${providerId}`;

function readCachedProviderModels(providerId: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(providerModelsCacheKey(providerId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as { models?: unknown };
    if (!Array.isArray(parsed?.models)) return [];
    return parsed.models.map((item) => String(item)).filter((item) => item.trim().length > 0);
  } catch {
    return [];
  }
}

function writeCachedProviderModels(providerId: string, models: string[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(providerModelsCacheKey(providerId), JSON.stringify({ models, updatedAt: new Date().toISOString() }));
}

function clearCachedProviderModels(providerId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(providerModelsCacheKey(providerId));
}

function ProviderManagement() {
  const providers = useDataStore((s) => s.providers);
  const createProvider = useDataStore((s) => s.createProvider);
  const updateProvider = useDataStore((s) => s.updateProvider);
  const deleteProvider = useDataStore((s) => s.deleteProvider);
  const setError = useUIStore((s) => s.setError);

  const [form, setForm] = useState({ ...defaultProviderForm });

  // 双击编辑状态：{ [providerId]: { [field]: currentValue } }
  const [editing, setEditing] = useState<Record<string, Record<string, string>>>({});
  // 删除确认
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  // 连接测试状态
  const [connectStates, setConnectStates] = useState<
    Record<string, { loading: boolean; models?: string[]; error?: string }>
  >({});
  // 聊天测试状态
  const [chatTestStates, setChatTestStates] = useState<
    Record<string, { loading: boolean; result?: ProviderChatTestResponse }>
  >({});
  // 用量数据缓存
  const [usageData, setUsageData] = useState<Record<string, ProviderUsageResponse>>({});

  useEffect(() => {
    setConnectStates((prev) => {
      const next = { ...prev };
      for (const provider of providers) {
        if (next[provider.id]?.models?.length) continue;
        const cachedModels = readCachedProviderModels(provider.id);
        if (cachedModels.length === 0) continue;
        next[provider.id] = { ...(next[provider.id] ?? { loading: false }), models: cachedModels };
      }
      return next;
    });
  }, [providers]);

  // 加载所有 Provider 用量
  useEffect(() => {
    const ids = providers.map((p) => p.id);
    ids.forEach(async (id) => {
      try {
        const data = await api.providerUsage(id);
        setUsageData((prev) => ({ ...prev, [id]: data }));
      } catch { /* ignore */ }
    });
  }, [providers]);

  const startEdit = (providerId: string, field: string, value: string) => {
    setEditing((prev) => ({
      ...prev,
      [providerId]: { ...prev[providerId], [field]: value }
    }));
  };

  const saveEdit = async (providerId: string, field: string) => {
    const value = editing[providerId]?.[field];
    if (value === undefined) return;
    try {
      await updateProvider(providerId, { [field]: value });
      setEditing((prev) => {
        const next = { ...prev };
        if (next[providerId]) {
          const { [field]: _, ...rest } = next[providerId];
          if (Object.keys(rest).length === 0) {
            delete next[providerId];
          } else {
            next[providerId] = rest;
          }
        }
        return next;
      });
    } catch { /* store 处理 */ }
  };

  const cancelEdit = (providerId: string, field: string) => {
    setEditing((prev) => {
      const next = { ...prev };
      if (next[providerId]) {
        const { [field]: _, ...rest } = next[providerId];
        if (Object.keys(rest).length === 0) {
          delete next[providerId];
        } else {
          next[providerId] = rest;
        }
      }
      return next;
    });
  };

  const handleConnect = async (providerId: string) => {
    setConnectStates((prev) => ({
      ...prev,
      [providerId]: {
        loading: true,
        models: prev[providerId]?.models,
      }
    }));
    try {
      const result = await api.providerModels(providerId);
      writeCachedProviderModels(providerId, result.models);
      setConnectStates((prev) => ({ ...prev, [providerId]: { loading: false, models: result.models } }));
    } catch (err) {
      setConnectStates((prev) => ({
        ...prev,
        [providerId]: {
          loading: false,
          models: prev[providerId]?.models,
          error: err instanceof Error ? err.message : "连接失败"
        }
      }));
    }
  };

  const handleToggleProviderModel = async (providerId: string, model: string, checked: boolean) => {
    const provider = providers.find((p) => p.id === providerId);
    if (!provider) return;
    const current = provider.available_models ?? [];
    const next = checked
      ? Array.from(new Set([...current, model]))
      : current.filter((item) => item !== model);
    try {
      await updateProvider(providerId, { available_models: next });
    } catch {
      // Store-level errors are surfaced elsewhere.
    }
  };

  const handleChatTest = async (providerId: string) => {
    setChatTestStates((prev) => ({ ...prev, [providerId]: { loading: true } }));
    try {
      const result = await api.providerChatTest(providerId);
      setChatTestStates((prev) => ({ ...prev, [providerId]: { loading: false, result } }));
    } catch (err) {
      setChatTestStates((prev) => ({
        ...prev,
        [providerId]: { loading: false, result: { ok: false, content: null, model: null, latency_ms: null, error: err instanceof Error ? err.message : "测试失败" } }
      }));
    }
  };

  const handleDelete = async (providerId: string) => {
    try {
      await deleteProvider(providerId);
      clearCachedProviderModels(providerId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeleteConfirmId(null);
    }
  };

  const isEditing = (providerId: string, field: string) =>
    editing[providerId]?.[field] !== undefined;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.api_key.trim()) return;
    try {
      await createProvider({
        provider_type: form.provider_type,
        name: form.name.trim(),
        base_url: form.base_url.trim() || null,
        api_key: form.api_key,
        supports_tools: form.supports_tools,
        supports_strict_schema: form.supports_strict_schema,
        strict_tool_schema: form.strict_tool_schema
      });
      setForm({ ...defaultProviderForm });
    } catch {
      // handled by store
    }
  };

  return (
    <>
      <PanelHeader icon={<KeyRound size={16} />} title="提供商配置详情" />

      {/* Provider cards */}
      {providers.length === 0 ? (
        <EmptyState
          title="暂无 Provider"
          description="填写下方表单创建真实 Provider。"
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-2 mb-4">
          {providers.map((p) => (
            <div
              key={p.id}
              className="border border-hairline rounded-lg bg-surface-canvas/50 p-3 relative group"
            >
              {/* Card header */}
              <header className="flex items-center justify-between gap-2 mb-3">
                <div className="min-w-0">
                  <strong className="block text-text-on-dark text-sm truncate">{p.name}</strong>
                  <span className="text-[10px] text-text-muted">{providerTypeLabel(p.provider_type)}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                    p.has_api_key ? "border-trading-fall/30 text-trading-fall" : "border-trading-rise/30 text-trading-rise"
                  }`}>
                    {p.has_api_key ? "已配置" : "未配置"}
                  </span>
                  <button
                    type="button"
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded text-text-muted hover:text-trading-rise hover:bg-surface-elevated"
                    title="删除 Provider"
                    onClick={() => setDeleteConfirmId(p.id)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </header>

              {/* Provider info */}
              <div className="grid gap-1.5 text-sm">
                <EditableRow
                  label="Base URL"
                  value={p.base_url || "未配置"}
                  editing={isEditing(p.id, "base_url")}
                  editValue={editing[p.id]?.["base_url"] ?? p.base_url}
                  onDoubleClick={() => startEdit(p.id, "base_url", p.base_url || "")}
                  onChange={(v) => setEditing((prev) => ({ ...prev, [p.id]: { ...prev[p.id], base_url: v } }))}
                  onSave={() => saveEdit(p.id, "base_url")}
                  onCancel={() => cancelEdit(p.id, "base_url")}
                />
                <div className="flex items-center gap-2 text-xs py-0.5">
                  <span className="text-text-muted w-[72px] shrink-0">Provider 类型</span>
                  <span className="text-text-body">{providerTypeLabel(p.provider_type)}</span>
                </div>
                <EditableRow
                  label="API Key"
                  value={p.api_key_masked || "未配置"}
                  editing={isEditing(p.id, "api_key")}
                  editValue={editing[p.id]?.["api_key"] ?? ""}
                  onDoubleClick={() => startEdit(p.id, "api_key", "")}
                  onChange={(v) => setEditing((prev) => ({ ...prev, [p.id]: { ...prev[p.id], api_key: v } }))}
                  onSave={() => saveEdit(p.id, "api_key")}
                  onCancel={() => cancelEdit(p.id, "api_key")}
                  placeholder="输入新 API Key（替换旧 Key）"
                />
                <div className="flex items-center gap-2 text-xs py-0.5">
                  <span className="text-text-muted w-[72px] shrink-0">Token 用量</span>
                  <span className="text-text-body font-mono">
                    {usageData[p.id]
                      ? `${formatTokens(usageData[p.id].total_tokens)} / ${usageData[p.id].total_runs} runs`
                      : "加载中..."}
                  </span>
                </div>
                {connectStates[p.id]?.models && connectStates[p.id]?.models!.length > 0 && (
                  <div className="grid gap-1.5 rounded-lg border border-hairline/60 bg-surface-canvas/40 p-2 max-h-40 overflow-auto">
                    {connectStates[p.id]?.models!.map((model) => (
                      <label key={model} className="flex items-center gap-2 text-xs text-text-body cursor-pointer">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 accent-brand-primary"
                          checked={p.available_models.includes(model)}
                          onChange={(e) => handleToggleProviderModel(p.id, model, e.target.checked)}
                        />
                        <span className="font-mono truncate" title={model}>{model}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {/* Connection / Chat Test */}
              <div className="flex flex-col gap-2 mt-3 pt-3 border-t border-hairline/50">
                <div className="flex items-center gap-2">
                  {/* Connect button */}
                  <button
                    type="button"
                    className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                      connectStates[p.id]?.loading ? "border-hairline text-text-muted cursor-wait"
                      : connectStates[p.id]?.error ? "border-trading-rise/30 text-trading-rise"
                      : connectStates[p.id]?.models ? "border-trading-fall/30 text-trading-fall"
                      : "border-hairline text-text-muted hover:border-brand-primary/30 hover:text-brand-primary"
                    }`}
                    onClick={() => handleConnect(p.id)}
                    disabled={connectStates[p.id]?.loading}
                  >
                    <span className="inline-flex items-center gap-1">
                      <Plug size={11} />
                      {connectStates[p.id]?.loading ? "连接中..." : connectStates[p.id]?.error ? `✗ ${connectStates[p.id]?.error!.slice(0, 30)}` : connectStates[p.id]?.models ? `✓ ${connectStates[p.id]?.models?.length ?? 0} 个模型` : "连接"}
                    </span>
                  </button>
                  {/* Chat test button */}
                  <button
                    type="button"
                    className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                      chatTestStates[p.id]?.loading ? "border-hairline text-text-muted cursor-wait"
                      : chatTestStates[p.id]?.result?.ok ? "border-trading-fall/30 text-trading-fall"
                      : chatTestStates[p.id]?.result && !chatTestStates[p.id]?.result?.ok ? "border-trading-rise/30 text-trading-rise"
                      : "border-hairline text-text-muted hover:border-brand-primary/30 hover:text-brand-primary"
                    }`}
                    onClick={() => handleChatTest(p.id)}
                    disabled={chatTestStates[p.id]?.loading}
                  >
                    <span className="inline-flex items-center gap-1">
                      <Zap size={11} />
                      {chatTestStates[p.id]?.loading ? "测试中..."
                      : chatTestStates[p.id]?.result?.ok ? `✓ ${chatTestStates[p.id]?.result?.latency_ms}ms`
                      : chatTestStates[p.id]?.result && !chatTestStates[p.id]?.result?.ok ? `✗ ${chatTestStates[p.id]?.result?.error?.slice(0, 30) ?? "失败"}`
                      : "测试"}
                    </span>
                  </button>
                </div>
                {/* Chat test result */}
                {chatTestStates[p.id]?.result && (
                  <div className={`text-[10px] leading-relaxed ${chatTestStates[p.id]?.result?.ok ? "text-trading-fall" : "text-trading-rise"}`}>
                    {chatTestStates[p.id]?.result?.ok
                      ? `回复: ${(chatTestStates[p.id]?.result?.content ?? "").slice(0, 80)}`
                      : `错误: ${chatTestStates[p.id]?.result?.error ?? "未知"}`}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create form */}
      <form
        className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2"
        onSubmit={handleSubmit}
      >
        <label className="grid gap-1.5 text-xs text-text-muted">
          Provider 类型
          <Select
            value={form.provider_type}
            onChange={(e) =>
              setForm({ ...form, provider_type: e.target.value })
            }
          >
            <option value="">请选择类型</option>
            <option value="deepseek">DeepSeek</option>
            <option value="openai_compatible">OpenAI-Compatible</option>
          </Select>
        </label>
        <Input
          label="名称"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Provider 名称"
        />
        <Input
          label="Base URL"
          value={form.base_url}
          onChange={(e) => setForm({ ...form, base_url: e.target.value })}
          placeholder="留空使用后端默认"
        />
        <Input
          label="API Key"
          type="password"
          value={form.api_key}
          onChange={(e) => setForm({ ...form, api_key: e.target.value })}
          placeholder="API Key"
        />
        <label className="grid gap-1.5 text-xs text-text-muted">
          <span>高级选项</span>
          <span className="flex flex-wrap gap-x-4 gap-y-1.5 bg-surface-canvas p-3 rounded-lg border border-hairline/50">
            {[
              { key: "supports_tools", label: "支持工具调用" },
              { key: "supports_strict_schema", label: "支持 Strict Schema" },
              { key: "strict_tool_schema", label: "强制严格 Schema" }
            ].map(({ key, label }) => (
              <label key={key} className="inline-flex items-center gap-1.5 cursor-pointer text-text-body">
                <input
                  type="checkbox"
                  className="accent-brand-primary h-4 w-4"
                  checked={Boolean(form[key as keyof typeof form])}
                  onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
                />
                {label}
              </label>
            ))}
          </span>
        </label>
        <div className="flex items-end">
          <Button
            variant="primary"
            icon={<Plus size={14} />}
            type="submit"
            disabled={!form.provider_type || !form.api_key.trim()}
          >
            保存 Provider
          </Button>
        </div>
      </form>

      {/* 删除确认弹窗 */}
      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-surface-canvas/70">
          <div className="w-[300px] rounded-xl border border-hairline bg-surface-card p-4 shadow-lg">
            <p className="text-sm text-text-on-dark mb-1 font-semibold">确认删除 Provider</p>
            <p className="text-xs text-text-muted mb-1">
              确定要删除「{providers.find((p) => p.id === deleteConfirmId)?.name ?? ""}」吗？
            </p>
            <p className="text-xs text-trading-rise mb-4">关联账号和会话不受影响（需先单独清理）。</p>
            <div className="flex justify-end gap-2">
              <button
                className="px-3 py-1.5 text-xs rounded-lg border border-hairline text-text-muted hover:text-text-on-dark hover:bg-surface-elevated transition-colors"
                type="button"
                onClick={() => setDeleteConfirmId(null)}
              >
                取消
              </button>
              <button
                className="px-3 py-1.5 text-xs rounded-lg bg-trading-rise text-white hover:bg-trading-rise/80 transition-colors"
                type="button"
                onClick={() => handleDelete(deleteConfirmId)}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  EditableRow                                                       */
/* ------------------------------------------------------------------ */

function EditableRow({
  label,
  value,
  editing,
  editValue,
  onDoubleClick,
  onChange,
  onSave,
  onCancel,
  placeholder = ""
}: {
  label: string;
  value: string;
  editing: boolean;
  editValue: string;
  onDoubleClick: () => void;
  onChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  placeholder?: string;
}) {
  if (editing) {
    return (
      <div className="flex items-center gap-2 text-xs py-0.5">
        <span className="text-text-muted w-[72px] shrink-0">{label}</span>
        <input
          autoFocus
          className="flex-1 h-7 px-2 rounded border border-brand-primary bg-surface-canvas text-text-on-dark text-xs focus:outline-none"
          value={editValue}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSave();
            if (e.key === "Escape") onCancel();
          }}
          onBlur={() => onSave()}
          placeholder={placeholder}
        />
        <button
          className="text-trading-fall text-[10px] hover:underline"
          type="button"
          onClick={onSave}
        >
          ✓
        </button>
        <button
          className="text-text-muted text-[10px] hover:underline"
          type="button"
          onClick={onCancel}
        >
          ✗
        </button>
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-2 text-xs py-0.5 cursor-pointer hover:bg-surface-elevated/30 rounded px-1 -mx-1 transition-colors group/row"
      onDoubleClick={onDoubleClick}
      title="双击编辑"
    >
      <span className="text-text-muted w-[72px] shrink-0">{label}</span>
      <span className="text-text-body font-mono truncate">{value}</span>
      <span className="opacity-0 group-hover/row:opacity-100 text-[10px] text-text-muted transition-opacity">
        双击编辑
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  TavilyManagement                                                  */
/* ------------------------------------------------------------------ */

const defaultTavilyForm = {
  api_key: "",
  default_search_depth: "basic",
  default_topic: "finance",
  default_max_results: "5",
  cache_ttl_seconds: "1800"
};

function TavilyManagement() {
  const [config, setConfig] = useState<TavilyConfig | null>(null);
  const [usage, setUsage] = useState<TavilyUsageResponse | null>(null);
  const [form, setForm] = useState({ ...defaultTavilyForm });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TavilyTestResponse | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [loadedConfig, loadedUsage] = await Promise.all([
        api.tavilyConfig(),
        api.tavilyUsage()
      ]);
      setConfig(loadedConfig);
      setUsage(loadedUsage);
      setForm({
        api_key: "",
        default_search_depth: loadedConfig.default_search_depth,
        default_topic: loadedConfig.default_topic,
        default_max_results: String(loadedConfig.default_max_results),
        cache_ttl_seconds: String(loadedConfig.cache_ttl_seconds)
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 Tavily 配置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        default_search_depth: form.default_search_depth,
        default_topic: form.default_topic,
        default_max_results: Number(form.default_max_results),
        cache_ttl_seconds: Number(form.cache_ttl_seconds)
      };
      if (form.api_key.trim()) payload.api_key = form.api_key.trim();
      const saved = await api.updateTavilyConfig(payload);
      setConfig(saved);
      setForm((current) => ({ ...current, api_key: "" }));
      setStatus("已保存");
      setTimeout(() => setStatus(null), 1800);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存 Tavily 配置失败");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testTavily();
      setTestResult(result);
      const loadedUsage = await api.tavilyUsage();
      setUsage(loadedUsage);
      setError(result.ok ? null : result.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tavily 测试失败");
    } finally {
      setTesting(false);
    }
  };

  return (
    <section className="grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <PanelHeader icon={<Search size={16} />} title="Tavily 搜索配置" />
        <Button
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={14} />}
          onClick={() => void load()}
        >
          刷新
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-trading-rise/40 bg-trading-rise/10 px-3 py-2 text-xs text-trading-rise">
          {error}
        </div>
      )}

      <form className="grid gap-3 rounded-lg border border-hairline bg-surface-canvas/35 p-3" onSubmit={handleSave}>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <Input
            label={config?.configured ? `API Key（${config.api_key_masked ?? "已配置"}）` : "API Key"}
            value={form.api_key}
            onChange={(event) => setForm({ ...form, api_key: event.target.value })}
            placeholder={config?.configured ? "留空则保留现有 Key" : "输入 Tavily API Key"}
          />
          <label className="grid gap-1.5 text-xs text-text-muted">
            搜索深度
            <Select
              value={form.default_search_depth}
              onChange={(event) => setForm({ ...form, default_search_depth: event.target.value })}
            >
              <option value="basic">basic（1 credit）</option>
              <option value="advanced">advanced（2 credits）</option>
            </Select>
          </label>
          <label className="grid gap-1.5 text-xs text-text-muted">
            默认主题
            <Select
              value={form.default_topic}
              onChange={(event) => setForm({ ...form, default_topic: event.target.value })}
            >
              <option value="finance">finance</option>
              <option value="news">news</option>
              <option value="general">general</option>
            </Select>
          </label>
          <Input
            label="最大结果数"
            type="number"
            min={1}
            max={20}
            value={form.default_max_results}
            onChange={(event) => setForm({ ...form, default_max_results: event.target.value })}
          />
          <Input
            label="缓存 TTL（秒）"
            type="number"
            min={0}
            max={604800}
            value={form.cache_ttl_seconds}
            onChange={(event) => setForm({ ...form, cache_ttl_seconds: event.target.value })}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" type="submit" disabled={saving || loading}>
            {saving ? "保存中" : "保存配置"}
          </Button>
          <Button
            variant="secondary"
            type="button"
            icon={<Search size={14} />}
            onClick={() => void handleTest()}
            disabled={testing || !config?.configured}
          >
            {testing ? "测试中" : "测试搜索"}
          </Button>
          {status && <span className="text-xs text-trading-fall">{status}</span>}
          {testResult && (
            <span className={`text-xs ${testResult.ok ? "text-trading-fall" : "text-trading-rise"}`}>
              {testResult.ok
                ? `测试成功：${testResult.result_count} 条 / ${testResult.credits_estimated} credit / ${testResult.latency_ms ?? "--"}ms`
                : testResult.error}
            </span>
          )}
        </div>
      </form>

      <section className="grid gap-3">
        <PanelHeader icon={<Zap size={16} />} title="调用统计" />
        <InfoGrid
          items={[
            ["总调用", String(usage?.total_calls ?? 0)],
            ["缓存命中", String(usage?.cache_hits ?? 0)],
            ["估算 Credits", String(usage?.credits_estimated ?? 0)],
            ["配置更新时间", config?.updated_at ? humanTime(config.updated_at) : "--"]
          ]}
        />
        {!usage || usage.recent.length === 0 ? (
          <EmptyState title="暂无 Tavily 调用" description="LLM 调用 Tavily 工具后这里会显示最近记录。" />
        ) : (
          <div className="max-h-[260px] overflow-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-muted text-xs border-b border-hairline">
                  <th className="pb-2 font-medium sticky top-0 bg-surface-card">时间</th>
                  <th className="pb-2 font-medium sticky top-0 bg-surface-card">操作</th>
                  <th className="pb-2 font-medium sticky top-0 bg-surface-card">状态</th>
                  <th className="pb-2 font-medium sticky top-0 bg-surface-card">结果</th>
                  <th className="pb-2 font-medium sticky top-0 bg-surface-card">Credits</th>
                  <th className="pb-2 font-medium sticky top-0 bg-surface-card">缓存</th>
                </tr>
              </thead>
              <tbody>
                {usage.recent.map((row) => (
                  <tr key={row.id} className="border-b border-hairline/50">
                    <td className="py-1.5 text-text-muted text-xs">{humanTime(row.created_at)}</td>
                    <td className="py-1.5 text-text-on-dark text-xs">{row.operation}</td>
                    <td className="py-1.5 text-text-muted text-xs">{row.status}</td>
                    <td className="py-1.5 text-text-muted text-xs">{row.result_count}</td>
                    <td className="py-1.5 text-text-muted text-xs">{row.credits_estimated}</td>
                    <td className="py-1.5 text-text-muted text-xs">{row.cache_hit ? "命中" : "未命中"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  ToolManagement                                                    */
/* ------------------------------------------------------------------ */

function ToolManagement() {
  const tools = useDataStore((s) => s.tools);
  const selectedToolFromStore = useUIStore((s) => s.selectedTool);

  const [selectedToolName, setSelectedToolName] = useState("");
  const [toolArgs, setToolArgs] = useState("{}");
  const [toolResult, setToolResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (selectedToolFromStore) {
      setSelectedToolName(selectedToolFromStore);
    }
  }, [selectedToolFromStore]);

  const selectedTool = useMemo(
    () => tools.find((t) => t.name === selectedToolName) ?? null,
    [selectedToolName, tools]
  );

  const handleTest = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedToolName) return;
    const args = parseInputObject(toolArgs);
    if (!args) return;
    try {
      const result = await api.testTool(selectedToolName, args);
      setToolResult(result);
    } catch {
      // handled by store
    }
  };

  return (
    <>
      <PanelHeader icon={<Wrench size={16} />} title="工具测试" />

      <form className="grid gap-3 mt-2" onSubmit={handleTest}>
        <label className="grid gap-1.5 text-xs text-text-muted">
          工具
          <Select
            value={selectedToolName}
            onChange={(e) => setSelectedToolName(e.target.value)}
            disabled={tools.length === 0}
          >
            <option value="">选择工具</option>
            {tools.map((t) => (
              <option key={t.name} value={t.name}>
                {t.display_name || t.name}
              </option>
            ))}
          </Select>
        </label>
        <Textarea
          value={toolArgs}
          onChange={(e) => setToolArgs(e.target.value)}
          placeholder='{"key": "value"}'
          spellCheck={false}
        />
        <Button
          variant="primary"
          icon={<Wrench size={14} />}
          type="submit"
          disabled={!selectedToolName}
        >
          运行工具测试
        </Button>
      </form>

      {/* Schema viewer */}
      {selectedTool ? (
        <div className="mt-4">
          <PanelHeader icon={<Code2 size={15} />} title="工具 Schema" />
          <RawJson data={selectedTool.parameters} />
        </div>
      ) : (
        <div className="mt-4">
          <EmptyState
            title="暂无工具"
            description="后端 /api/tools 未返回工具，或尚未选择工具。"
          />
        </div>
      )}

      {/* Result viewer */}
      {toolResult && (
        <div className="mt-4">
          <PanelHeader icon={<CheckCircle2 size={15} />} title="调用结果" />
          <RawJson data={toolResult} />
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  UsageManagement                                                   */
/* ------------------------------------------------------------------ */

function UsageManagement() {
  const [usage, setUsage] = useState<UsageSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadUsage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setUsage(await api.usageSummary());
    } catch (err) {
      setError(err instanceof Error ? err.message : "用量数据加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUsage();
  }, [loadUsage]);

  if (loading && !usage) {
    return (
      <section>
        <PanelHeader icon={<BarChart3 size={16} />} title="用量与归因分析" />
        <p className="mt-3 text-sm text-text-muted">加载中...</p>
      </section>
    );
  }

  const summary = usage?.summary;

  return (
    <section className="grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <PanelHeader icon={<BarChart3 size={16} />} title="用量与归因分析" />
        <Button
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={14} />}
          onClick={() => void loadUsage()}
          disabled={loading}
        >
          刷新
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-trading-rise/40 bg-trading-rise/10 px-3 py-2 text-sm text-trading-rise">
          {error}
        </div>
      )}

      {!summary || summary.llm_calls === 0 ? (
        <EmptyState
          title="暂无 LLM 用量"
          description="Session 运行后，这里会展示真实 token 消耗与超限记录。"
        />
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
            <MetricBox label="总 Token" value={formatTokens(summary.total_tokens)} />
            <MetricBox label="Prompt" value={formatTokens(summary.prompt_tokens)} />
            <MetricBox label="Completion" value={formatTokens(summary.completion_tokens)} />
            <MetricBox label="Thinking" value={formatTokens(summary.thinking_tokens)} />
            <MetricBox label="LLM 调用" value={String(summary.llm_calls)} />
            <MetricBox label="平均耗时" value={formatLatency(summary.avg_latency_ms)} />
            <MetricBox label="超限" value={String(summary.cap_exceeded_count)} danger={summary.cap_exceeded_count > 0} />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
            <UsageGroupTable title="Provider" rows={usage.by_provider} />
            <UsageGroupTable title="模型" rows={usage.by_model} />
            <UsageGroupTable title="Session" rows={usage.by_session} />
          </div>

          <section>
            <PanelHeader icon={<Activity size={15} />} title="最近 Run" />
            <UsageRunTable rows={usage.recent_runs} />
          </section>
        </>
      )}
    </section>
  );
}

function MetricBox({
  label,
  value,
  danger = false
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="rounded-lg border border-hairline bg-surface-canvas/50 p-3">
      <span className="block text-xs text-text-muted">{label}</span>
      <strong className={`mt-1 block text-lg ${danger ? "text-trading-rise" : "text-text-on-dark"}`}>
        {value}
      </strong>
    </div>
  );
}

function UsageGroupTable({ title, rows }: { title: string; rows: UsageGroupRow[] }) {
  return (
    <section className="rounded-lg border border-hairline bg-surface-canvas/40 p-3">
      <PanelHeader icon={<BarChart3 size={15} />} title={title} />
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">暂无数据。</p>
      ) : (
        <div className="mt-2 max-h-[260px] overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-muted text-xs border-b border-hairline">
                <th className="pb-2 font-medium">名称</th>
                <th className="pb-2 font-medium">Token</th>
                <th className="pb-2 font-medium">调用</th>
                <th className="pb-2 font-medium">均耗时</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${title}-${row.id ?? row.name}`} className="border-b border-hairline/50">
                  <td className="py-1.5 text-text-on-dark">{row.name ?? row.id ?? "--"}</td>
                  <td className="py-1.5 text-text-muted font-mono">{formatTokens(row.total_tokens)}</td>
                  <td className="py-1.5 text-text-muted">{row.llm_calls}</td>
                  <td className="py-1.5 text-text-muted">{formatLatency(row.avg_latency_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function UsageRunTable({ rows }: { rows: UsageRunRow[] }) {
  if (rows.length === 0) {
    return <EmptyState title="暂无 Run 用量" description="LLM 运行完成后会记录每次调用的 token。" />;
  }
  return (
    <div className="mt-2 max-h-[360px] overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-text-muted text-xs border-b border-hairline">
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">时间</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">Session</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">模型</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">Token</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">耗时</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">调用</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">状态</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.run_id ?? `${row.session_id}-${row.created_at}`} className="border-b border-hairline/50">
              <td className="py-1.5 text-text-muted">{humanTime(row.created_at)}</td>
              <td className="py-1.5 text-text-on-dark">{row.session_name}</td>
              <td className="py-1.5 text-text-muted">{row.model}</td>
              <td className="py-1.5 text-text-on-dark font-mono">{formatTokens(row.total_tokens)}</td>
              <td className="py-1.5 text-text-muted">{formatLatency(row.latency_ms)}</td>
              <td className="py-1.5 text-text-muted">{row.llm_calls}</td>
              <td className={`py-1.5 ${row.cap_exceeded_count > 0 ? "text-trading-rise" : "text-text-muted"}`}>
                {row.cap_exceeded_count > 0 ? "超限" : "正常"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  DataManagement                                                    */
/* ------------------------------------------------------------------ */

function DataManagement() {
  const dataFetchForm = useMarketStore((s) => s.dataFetchForm);
  const setDataFetchForm = useMarketStore((s) => s.setDataFetchForm);
  const dataFetchResult = useMarketStore((s) => s.dataFetchResult);
  const cacheRows = useMarketStore((s) => s.cacheRows);
  const conflicts = useMarketStore((s) => s.conflicts);
  const fetchHistory = useMarketStore((s) => s.fetchHistory);
  const resolveConflict = useMarketStore((s) => s.resolveConflict);

  const handleFetch = async (e: FormEvent) => {
    e.preventDefault();
    if (!dataFetchForm.symbol.trim() || !dataFetchForm.start || !dataFetchForm.end) return;
    try {
      await fetchHistory(
        dataFetchForm.symbol.trim(),
        dataFetchForm.start,
        dataFetchForm.end,
        dataFetchForm.adjust || undefined
      );
    } catch {
      // handled by store
    }
  };

  const handleResolve = useCallback(
    (id: string, status: "resolved" | "ignored") => {
      void resolveConflict(id, status);
    },
    [resolveConflict]
  );

  const [refreshingCache, setRefreshingCache] = useState(false);
  const handleRefreshCache = async () => {
    setRefreshingCache(true);
    try {
      const rows = await api.cacheStatus();
      useMarketStore.setState({ cacheRows: rows });
    } finally {
      setRefreshingCache(false);
    }
  };

  return (
    <div className="grid gap-4">
      <PanelHeader icon={<Database size={16} />} title="历史数据拉取" />

      <form className="flex flex-wrap items-end gap-3" onSubmit={handleFetch}>
        <Input
          label="股票代码"
          value={dataFetchForm.symbol}
          onChange={(e) =>
            setDataFetchForm({ ...dataFetchForm, symbol: e.target.value })
          }
          placeholder="输入股票代码"
        />
        <Input
          label="起始日期"
          type="date"
          value={dataFetchForm.start}
          onChange={(e) =>
            setDataFetchForm({ ...dataFetchForm, start: e.target.value })
          }
        />
        <Input
          label="结束日期"
          type="date"
          value={dataFetchForm.end}
          onChange={(e) =>
            setDataFetchForm({ ...dataFetchForm, end: e.target.value })
          }
        />
        <label className="grid gap-1.5 text-xs text-text-muted">
          复权
          <Select
            value={dataFetchForm.adjust}
            onChange={(e) =>
              setDataFetchForm({ ...dataFetchForm, adjust: e.target.value })
            }
          >
            <option value="">不复权</option>
            <option value="qfq">前复权</option>
            <option value="hfq">后复权</option>
          </Select>
        </label>
        <Button
          variant="primary"
          icon={<Database size={14} />}
          type="submit"
          disabled={
            !dataFetchForm.symbol.trim() ||
            !dataFetchForm.start ||
            !dataFetchForm.end
          }
        >
          拉取并写入缓存
        </Button>
      </form>

      {/* Fetch result */}
      {dataFetchResult && (
        <section>
          <InfoGrid
            items={[
              ["股票代码", dataFetchResult.symbol],
              ["拉取", String(dataFetchResult.fetched)],
              ["写入", String(dataFetchResult.inserted)],
              ["跳过", String(dataFetchResult.skipped)],
              ["冲突", String(dataFetchResult.conflicted)],
              ["复权", dataFetchResult.adjust || "不复权"]
            ]}
          />
        </section>
      )}

      {/* Cache status */}
      <section>
        <div className="flex items-center justify-between">
          <PanelHeader icon={<Database size={15} />} title="缓存状态" />
          <button
            type="button"
            className={`p-1.5 rounded-md hover:bg-surface-elevated transition-colors disabled:opacity-50 ${refreshingCache ? "animate-spin" : ""}`}
            onClick={handleRefreshCache}
            disabled={refreshingCache}
            title="刷新缓存状态"
          >
            <RefreshCw size={14} className="text-text-muted" />
          </button>
        </div>
        <CacheStatusTable rows={cacheRows} />
      </section>

      {/* Conflicts */}
      <section>
        <PanelHeader icon={<AlertTriangle size={15} />} title="数据冲突" />
        <ConflictsTable
          conflicts={conflicts}
          onResolve={handleResolve}
        />
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CacheStatusTable                                                  */
/* ------------------------------------------------------------------ */

function CacheStatusTable({ rows }: { rows: CacheStatusRow[] }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="暂无缓存"
        description="调用历史行情拉取后，这里会显示真实缓存覆盖范围。"
      />
    );
  }

  return (
    <div className="max-h-[240px] overflow-auto mt-1">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-text-muted text-xs border-b border-hairline">
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">代码</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">名称</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">周期</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">复权</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">起始</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">结束</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">记录</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">更新时间</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.symbol}-${row.interval}-${row.adjust}`}
              className="border-b border-hairline/50"
            >
              <td className="py-1.5 text-text-on-dark text-xs">{row.symbol}</td>
              <td className="py-1.5 text-text-muted text-xs">{row.name ?? "--"}</td>
              <td className="py-1.5 text-text-muted text-xs">{row.interval}</td>
              <td className="py-1.5 text-text-muted text-xs">
                {row.adjust || "不复权"}
              </td>
              <td className="py-1.5 text-text-muted text-xs font-mono">
                {row.start_datetime}
              </td>
              <td className="py-1.5 text-text-muted text-xs font-mono">
                {row.end_datetime}
              </td>
              <td className="py-1.5 text-text-on-dark text-xs">{row.bar_count}</td>
              <td className="py-1.5 text-text-muted text-xs">
                {humanTime(row.updated_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ConflictsTable                                                    */
/* ------------------------------------------------------------------ */

function ConflictsTable({
  conflicts,
  onResolve
}: {
  conflicts: DataConflict[];
  onResolve: (id: string, status: "resolved" | "ignored") => void;
}) {
  if (conflicts.length === 0) {
    return (
      <EmptyState
        title="暂无冲突"
        description="数据写入出现冲突时，这里会显示待处理记录。"
      />
    );
  }

  return (
    <div className="max-h-[240px] overflow-auto mt-1">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-text-muted text-xs border-b border-hairline">
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">代码</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">时间</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">周期</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">复权</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">来源</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">差异</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">状态</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">操作</th>
          </tr>
        </thead>
        <tbody>
          {conflicts.map((c) => (
            <tr key={c.id} className="border-b border-hairline/50">
              <td className="py-1.5 text-text-on-dark text-xs">{c.symbol}</td>
              <td className="py-1.5 text-text-muted text-xs font-mono">{c.datetime}</td>
              <td className="py-1.5 text-text-muted text-xs">{c.interval}</td>
              <td className="py-1.5 text-text-muted text-xs">
                {c.adjust || "不复权"}
              </td>
              <td className="py-1.5 text-text-muted text-xs">{c.source}</td>
              <td className="py-1.5 text-text-muted text-xs">
                {conflictSummary(c)}
              </td>
              <td className="py-1.5 text-text-muted text-xs">{c.status}</td>
              <td className="py-1.5">
                <div className="flex gap-1.5">
                  <button
                    className="text-brand-primary text-xs hover:underline"
                    type="button"
                    onClick={() => onResolve(c.id, "resolved")}
                  >
                    标记解决
                  </button>
                  <button
                    className="text-text-muted text-xs hover:underline"
                    type="button"
                    onClick={() => onResolve(c.id, "ignored")}
                  >
                    忽略
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section Placeholders                                              */
/* ------------------------------------------------------------------ */

function SkillsPlaceholder() {
  return (
    <section>
      <PanelHeader icon={<Bot size={16} />} title="Skills 管理" />
      <div className="mt-3 p-4 border border-hairline rounded-lg bg-surface-canvas/30">
        <p className="text-text-muted text-xs mb-4">
          后端尚未提供 Skills CRUD 接口。以下为前端预留表单示意，后端 API 接入后立即可用：
        </p>
        <form className="grid gap-3" onSubmit={(e) => e.preventDefault()}>
          <Input label="Skill 名称" disabled placeholder="例如：短线交易员、价值投资者" />
          <label className="grid gap-1.5 text-xs text-text-muted">
            Skill Prompt
            <Textarea
              disabled
              placeholder="定义角色行为、交易策略、风控规则..."
              rows={4}
            />
          </label>
          <label className="grid gap-1.5 text-xs text-text-muted">
            Tool 白名单
            <span className="px-3 py-3 mt-1 text-xs text-text-muted border border-dashed border-hairline rounded bg-surface-canvas/30">
              后端 /api/tools 返回的工具将在此列出，支持启用/禁用
            </span>
          </label>
          <div className="flex gap-2">
            <Button variant="primary" disabled icon={<Plus size={14} />}>
              保存 Skill
            </Button>
            <Button variant="secondary" disabled>
              上传 Skill 文件
            </Button>
          </div>
        </form>
      </div>
      <EmptyState
        title="等待后端接入"
        description="Skills CRUD、版本管理、Tool 白名单配置、Session 绑定等能力依赖后端 API。"
      />
    </section>
  );
}

function TriggersPlaceholder() {
  return (
    <section>
      <PanelHeader icon={<Bell size={16} />} title="触发器管理" />
      <div className="mt-3 p-4 border border-hairline rounded-lg bg-surface-canvas/30">
        <p className="text-text-muted text-xs mb-4">
          后端尚未接入触发器 CRUD 和调度控制。以下为前端预留表单示意：
        </p>
        <form className="grid gap-3" onSubmit={(e) => e.preventDefault()}>
          <Input label="触发器名称" disabled placeholder="例如：每日开盘前检查" />
          <label className="grid gap-1.5 text-xs text-text-muted">
            触发类型
            <Select value="cron" disabled>
              <option value="cron">定时触发 (Cron)</option>
              <option value="interval">间隔触发</option>
              <option value="once">单次触发</option>
            </Select>
          </label>
          <Input label="Cron 表达式" disabled placeholder="0 9 30 * * 1-5（周一到周五 09:30）" />
          <label className="grid gap-1.5 text-xs text-text-muted">
            绑定 Session
            <Select value="" disabled>
              <option value="">选择 Session</option>
            </Select>
          </label>
          <label className="grid gap-1.5 text-xs text-text-muted">
            事件 Prompt
            <Textarea
              disabled
              placeholder="注入给 LLM 的消息内容，例如：现在是开盘时间，请分析当前市场..."
              rows={3}
            />
          </label>
          <div className="flex gap-2">
            <Button variant="primary" disabled icon={<Plus size={14} />}>
              创建触发器
            </Button>
            <Button variant="secondary" disabled>
              立即运行
            </Button>
          </div>
        </form>
      </div>
      <EmptyState
        title="等待后端接入"
        description="触发器 CRUD、Cron/Interval/Once 调度、Session 绑定、运行状态查询等能力依赖后端 API。"
      />
    </section>
  );
}

function SystemSettings() {
  const providers = useDataStore((s) => s.providers);
  const systemModel = useUIStore((s) => s.systemModel);
  const setSystemProviderId = useUIStore((s) => s.setSystemProviderId);
  const setSystemModel = useUIStore((s) => s.setSystemModel);

  const [model, setModel] = useState(systemModel ?? "");
  const [saved, setSaved] = useState(false);
  const modelOptions = useMemo(() => providerModelOptions(providers), [providers]);
  const selectedModelValue = modelOptions.some((option) => option.value === model) ? model : "";

  const handleSave = (e: FormEvent) => {
    e.preventDefault();
    const selected = resolveProviderByModelValue(providers, selectedModelValue);
    setSystemProviderId(selected?.providerId ?? null);
    setSystemModel(selected ? selectedModelValue : null);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <section>
      <PanelHeader icon={<Settings size={16} />} title="系统设置" />
      <div className="mt-3 p-4 border border-hairline rounded-lg">
        <form className="grid gap-3" onSubmit={handleSave}>
          <label className="grid gap-1.5 text-xs text-text-muted">
            系统模型
            <Select
              value={selectedModelValue}
              onChange={(e) => setModel(e.target.value)}
              disabled={modelOptions.length === 0}
            >
              <option value="">{modelOptions.length > 0 ? "不指定" : "请先在 Provider 中勾选可用模型"}</option>
              {modelOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </Select>
          </label>
          <div className="flex gap-2 items-center">
            <Button variant="primary" type="submit">
              {saved ? "已保存" : "保存设置"}
            </Button>
            {saved && <CheckCircle2 size={14} className="text-trading-fall" />}
          </div>
        </form>
      </div>

      <div className="mt-3 p-4 border border-hairline rounded-lg bg-surface-canvas/30">
        <p className="text-text-muted text-xs mb-4">
          以下设置依赖后端 API，当前为占位示意：
        </p>
        <form className="grid gap-3" onSubmit={(e) => e.preventDefault()}>
          <label className="grid gap-1.5 text-xs text-text-muted">
            默认基准指数
            <Select value="" disabled>
              <option value="">沪深300</option>
              <option value="sh">上证指数</option>
              <option value="sz50">上证50</option>
              <option value="zz500">中证500</option>
              <option value="cyb">创业板指</option>
            </Select>
          </label>
          <label className="grid gap-1.5 text-xs text-text-muted">
            默认行情周期
            <Select value="daily" disabled>
              <option value="daily">日线</option>
              <option value="weekly">周线</option>
              <option value="monthly">月线</option>
            </Select>
          </label>
          <Input label="模拟交易起始日期" disabled type="date" />
          <label className="grid gap-1.5 text-xs text-text-muted">
            日志级别
            <Select value="info" disabled>
              <option value="debug">调试</option>
              <option value="info">信息</option>
              <option value="warning">警告</option>
              <option value="error">错误</option>
            </Select>
          </label>
          <div className="flex gap-2">
            <Button variant="primary" disabled>
              保存设置
            </Button>
          </div>
        </form>
      </div>
      <EmptyState
        title="后端接入后可启用完整设置"
        description="系统设置读写、日志查询、数据备份、全局参数配置等能力依赖后端 API。"
      />
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Section Icons                                                     */
/* ------------------------------------------------------------------ */

function sectionIcon(section: string) {
  const size = 15;
  if (section === "模型与API") return <KeyRound size={size} />;
  if (section === "提示词") return <Code2 size={size} />;
  if (section === "Tavily") return <Search size={size} />;
  if (section === "用量分析") return <BarChart3 size={size} />;
  if (section === "Skills") return <Bot size={size} />;
  if (section === "Tools") return <Wrench size={size} />;
  if (section === "触发器") return <Bell size={size} />;
  if (section === "数据管理") return <Database size={size} />;
  return <Settings size={size} />;
}

function formatTokens(value: number | null | undefined): string {
  const num = Number(value ?? 0);
  if (!Number.isFinite(num)) return "--";
  return new Intl.NumberFormat("zh-CN").format(num);
}

function formatLatency(value: number | null | undefined): string {
  if (value == null) return "--";
  const num = Number(value);
  if (!Number.isFinite(num)) return "--";
  if (num >= 1000) return `${(num / 1000).toFixed(1)}s`;
  return `${Math.round(num)}ms`;
}
