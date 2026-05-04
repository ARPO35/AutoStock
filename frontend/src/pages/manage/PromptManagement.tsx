import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, ChevronDown, Download, Plus, Trash2, Upload, X } from "lucide-react";
import type { PromptEntry, PromptRole } from "@/api";
import { api } from "@/api";
import { Button } from "@/components/ui/Button";
import { EmptyState, PanelHeader } from "@/components/ui/Shared";
import { Textarea } from "@/components/ui/Input";

type EditableEntry = PromptEntry & { local?: boolean };
type EditableRole = Omit<PromptRole, "entries"> & { entries: EditableEntry[] };

const builtinRefs = new Set(["system", "UserInput"]);

function cloneRole(role: PromptRole): EditableRole {
  return {
    ...role,
    entries: role.entries.map((entry) => ({ ...entry }))
  };
}

function nextRef(entries: EditableEntry[]): string {
  let index = 1;
  while (entries.some((entry) => entry.ref_name === `custom_${index}`)) index += 1;
  return `custom_${index}`;
}

function rolePayload(role: EditableRole) {
  return {
    name: role.name,
    entries: role.entries.map((entry) => ({
      id: entry.local ? undefined : entry.id,
      name: entry.name,
      ref_name: entry.ref_name,
      content: entry.content,
      enabled: entry.enabled,
      builtin: entry.builtin
    }))
  };
}

export function PromptManagement() {
  const [roles, setRoles] = useState<PromptRole[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditableRole | null>(null);
  const [rolePanelOpen, setRolePanelOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const selectedRole = useMemo(
    () => roles.find((role) => role.id === selectedRoleId) ?? roles[0] ?? null,
    [roles, selectedRoleId]
  );

  const refreshRoles = async (nextSelectedId?: string) => {
    setLoading(true);
    try {
      const loaded = await api.promptRoles();
      setRoles(loaded);
      const selected = nextSelectedId
        ? loaded.find((role) => role.id === nextSelectedId) ?? loaded[0] ?? null
        : loaded.find((role) => role.id === selectedRoleId) ?? loaded[0] ?? null;
      setSelectedRoleId(selected?.id ?? null);
      setDraft(selected ? cloneRole(selected) : null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载提示词失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshRoles();
  }, []);

  useEffect(() => {
    if (selectedRole) setDraft(cloneRole(selectedRole));
  }, [selectedRole?.id]);

  const updateEntry = (entryId: string, patch: Partial<EditableEntry>) => {
    setDraft((current) => current
      ? {
          ...current,
          entries: current.entries.map((entry) =>
            entry.id === entryId ? { ...entry, ...patch } : entry
          )
        }
      : current);
  };

  const handleCreateRole = async () => {
    try {
      const created = await api.createPromptRole({ name: "新角色" });
      await refreshRoles(created.id);
      setRolePanelOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建角色失败");
    }
  };

  const handleDeleteRole = async (roleId: string) => {
    if (roleId === "default") return;
    try {
      await api.deletePromptRole(roleId);
      await refreshRoles("default");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除角色失败");
    }
  };

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const saved = await api.updatePromptRole(draft.id, rolePayload(draft));
      await refreshRoles(saved.id);
      setStatus("已保存");
      setTimeout(() => setStatus(null), 1800);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存提示词失败");
    } finally {
      setSaving(false);
    }
  };

  const handleAddPrompt = () => {
    if (!draft) return;
    const ref = nextRef(draft.entries);
    setDraft({
      ...draft,
      entries: [
        ...draft.entries,
        {
          id: `local-${Date.now()}`,
          role_id: draft.id,
          name: "自定义提示词",
          ref_name: ref,
          content: "",
          enabled: true,
          builtin: false,
          sort_order: draft.entries.length,
          created_at: "",
          updated_at: "",
          local: true
        }
      ]
    });
  };

  const handleExport = async () => {
    if (!selectedRole) return;
    try {
      const exported = await api.exportPromptRole(selectedRole.id);
      const blob = new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${exported.name || "prompt-role"}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出失败");
    }
  };

  const handleImportFile = async (file: File | null) => {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as PromptRole;
      const imported = await api.importPromptRole({
        name: parsed.name,
        entries: parsed.entries.map((entry) => ({
          name: entry.name,
          ref_name: entry.ref_name,
          content: entry.content,
          enabled: entry.enabled,
          builtin: entry.builtin
        }))
      });
      await refreshRoles(imported.id);
      setRolePanelOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    }
  };

  return (
    <section>
      <PanelHeader icon={<Bot size={16} />} title="提示词" />

      <div className="relative mb-3 flex items-center justify-between gap-3 border border-hairline rounded-lg bg-surface-canvas/40 p-3">
        <button
          type="button"
          className="min-w-[220px] h-9 inline-flex items-center justify-between gap-3 rounded-md border border-hairline bg-surface-card px-3 text-sm text-text-on-dark hover:bg-surface-elevated transition-colors"
          onClick={() => setRolePanelOpen(true)}
        >
          <span className="truncate">{draft?.name ?? "选择角色"}</span>
          <ChevronDown size={15} className="text-text-muted" />
        </button>
        <div className="flex items-center gap-2">
          {status && <span className="text-xs text-trading-fall">{status}</span>}
          <Button variant="secondary" size="sm" onClick={() => void refreshRoles()}>
            刷新
          </Button>
          <Button variant="primary" size="sm" onClick={handleSave} disabled={!draft || saving}>
            {saving ? "保存中" : "保存"}
          </Button>
        </div>

        {rolePanelOpen && (
          <div className="fixed inset-0 z-40 bg-surface-canvas/70 backdrop-blur-sm" onClick={() => setRolePanelOpen(false)}>
            <div
              className="absolute left-1/2 top-[120px] w-[440px] -translate-x-1/2 rounded-xl border border-hairline bg-surface-card p-3 shadow-2xl"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex items-center justify-between gap-2 border-b border-hairline pb-2">
                <strong className="text-sm text-text-on-dark">角色配置</strong>
                <button type="button" className="text-text-muted hover:text-text-on-dark" onClick={() => setRolePanelOpen(false)}>
                  <X size={16} />
                </button>
              </div>
              <div className="mt-3 flex gap-2">
                <Button variant="secondary" size="sm" icon={<Upload size={13} />} onClick={() => importInputRef.current?.click()}>
                  导入
                </Button>
                <Button variant="secondary" size="sm" icon={<Download size={13} />} onClick={handleExport} disabled={!selectedRole}>
                  导出
                </Button>
                <Button variant="primary" size="sm" icon={<Plus size={13} />} onClick={handleCreateRole}>
                  新建
                </Button>
                <input
                  ref={importInputRef}
                  type="file"
                  accept="application/json,.json"
                  className="hidden"
                  onChange={(event) => void handleImportFile(event.target.files?.[0] ?? null)}
                />
              </div>
              <div className="mt-3 max-h-[360px] overflow-auto">
                {roles.map((role) => (
                  <div
                    key={role.id}
                    className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                      role.id === selectedRoleId
                        ? "bg-brand-primary/10 text-brand-primary"
                        : "text-text-body hover:bg-surface-elevated"
                    }`}
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => {
                        setSelectedRoleId(role.id);
                        setDraft(cloneRole(role));
                        setRolePanelOpen(false);
                      }}
                    >
                      <span className="block truncate">{role.name}</span>
                    </button>
                    <button
                      type="button"
                      className="grid h-7 w-7 place-items-center rounded text-text-muted hover:text-trading-rise disabled:opacity-40"
                      disabled={role.id === "default"}
                      title={role.id === "default" ? "默认角色不可删除" : "删除角色"}
                      onClick={() => void handleDeleteRole(role.id)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-trading-rise/40 bg-trading-rise/10 px-3 py-2 text-xs text-trading-rise">
          {error}
        </div>
      )}

      {loading ? (
        <EmptyState title="加载中" description="正在读取提示词角色配置。" />
      ) : !draft ? (
        <EmptyState title="暂无角色" description="创建角色后即可编辑提示词。" />
      ) : (
        <div className="grid gap-3">
          <label className="grid gap-1.5 text-xs text-text-muted">
            角色名称
            <input
              className="h-10 rounded-lg border border-hairline bg-surface-card px-3 text-sm text-text-on-dark focus:border-info focus:ring-2 focus:ring-info/50"
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
          </label>

          {draft.entries.map((entry) => (
            <PromptEntryEditor
              key={entry.id}
              entry={entry}
              onChange={(patch) => updateEntry(entry.id, patch)}
              onDelete={() => setDraft({
                ...draft,
                entries: draft.entries.filter((item) => item.id !== entry.id)
              })}
            />
          ))}

          <button
            type="button"
            className="grid h-10 place-items-center rounded-lg border border-dashed border-hairline text-text-muted hover:border-brand-primary/40 hover:text-brand-primary transition-colors"
            onClick={handleAddPrompt}
          >
            <Plus size={16} />
          </button>
        </div>
      )}
    </section>
  );
}

function PromptEntryEditor({
  entry,
  onChange,
  onDelete
}: {
  entry: EditableEntry;
  onChange: (patch: Partial<EditableEntry>) => void;
  onDelete: () => void;
}) {
  const [editingName, setEditingName] = useState(false);
  const [editingRef, setEditingRef] = useState(false);
  const locked = entry.builtin || builtinRefs.has(entry.ref_name);

  return (
    <section className="rounded-lg border border-hairline bg-surface-canvas/35 p-3">
      <div className="mb-2 flex items-center gap-2">
        {editingName && !locked ? (
          <input
            className="h-7 w-[180px] rounded border border-hairline bg-surface-card px-2 text-sm text-text-on-dark"
            value={entry.name}
            autoFocus
            onChange={(event) => onChange({ name: event.target.value })}
            onBlur={() => setEditingName(false)}
            onKeyDown={(event) => {
              if (event.key === "Enter") setEditingName(false);
            }}
          />
        ) : (
          <strong
            className={`text-sm text-text-on-dark ${locked ? "" : "cursor-text"}`}
            onDoubleClick={() => !locked && setEditingName(true)}
          >
            {entry.name}
          </strong>
        )}
        {editingRef && !locked ? (
          <input
            className="h-7 w-[150px] rounded border border-hairline bg-surface-card px-2 text-xs text-text-muted"
            value={entry.ref_name}
            autoFocus
            onChange={(event) => onChange({ ref_name: event.target.value })}
            onBlur={() => setEditingRef(false)}
            onKeyDown={(event) => {
              if (event.key === "Enter") setEditingRef(false);
            }}
          />
        ) : (
          <span
            className={`text-xs text-text-muted ${locked ? "" : "cursor-text"}`}
            onDoubleClick={() => !locked && setEditingRef(true)}
          >
            {`{${entry.ref_name}}`}
          </span>
        )}
        <label className="ml-auto inline-flex items-center gap-1.5 text-xs text-text-muted">
          <input
            type="checkbox"
            checked={entry.enabled}
            onChange={(event) => onChange({ enabled: event.target.checked })}
          />
          开启
        </label>
        {!locked && (
          <button type="button" className="text-text-muted hover:text-trading-rise" onClick={onDelete} title="删除提示词">
            <Trash2 size={14} />
          </button>
        )}
      </div>
      <Textarea
        rows={entry.ref_name === "system" ? 6 : 4}
        value={entry.content}
        onChange={(event) => onChange({ content: event.target.value })}
        placeholder={entry.ref_name === "system" ? "输入 role=system 的系统提示词" : "输入提示词模板，可使用 {引用名}"}
      />
    </section>
  );
}
