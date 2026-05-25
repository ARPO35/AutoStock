import { type ReactNode, useState } from "react";
import { Save, Plus, ShieldAlert, MessageSquare } from "lucide-react";
import { useDataStore } from "@/stores/dataStore";
import { useUIStore, editTabs } from "@/stores/uiStore";
import { EmptyState, PanelHeader, SubTabs } from "@/components/ui/Shared";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";

/* ------------------------------------------------------------------ */
/*  Page shell                                                        */
/* ------------------------------------------------------------------ */

export function EditPage() {
  const editTab = useUIStore((s) => s.editTab);
  const setEditTab = useUIStore((s) => s.setEditTab);

  return (
    <section className="flex flex-col min-h-0 overflow-auto p-4 gap-3">
      <PageHeader
        eyebrow={`修改 - ${editTab}`}
        title="人工修改账户状态与 Session 绑定，所有变更进入审计记录"
        actions={
          <>
            <Button variant="secondary" size="sm" disabled>
              取消
            </Button>
            <Button variant="primary" size="sm" icon={<Save size={14} />} disabled>
              保存
            </Button>
          </>
        }
      />

      <SubTabs tabs={editTabs} active={editTab} onChange={setEditTab} />

      {(editTab === "账户信息" || editTab === "会话绑定") ? (
        <EditForms />
      ) : (
        <PlaceholderSection
          title={editTab}
          description={editTabDesc(editTab)}
        />
      )}
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
    <header className="flex items-center justify-between gap-3.5 mb-1">
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
/*  EditForms  (Create Account + Create Session)                      */
/* ------------------------------------------------------------------ */

function EditForms() {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const createAccount = useDataStore((s) => s.createAccount);
  const createSession = useDataStore((s) => s.createSession);

  const [accountName, setAccountName] = useState("");
  const [accountInitialCash, setAccountInitialCash] = useState("");

  const [sessionName, setSessionName] = useState("");
  const [sessionAccountId, setSessionAccountId] = useState("");

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accountName.trim()) return;
    const payload: Record<string, unknown> = {
      name: accountName.trim()
    };
    if (accountInitialCash.trim()) {
      payload.initial_cash = Number(accountInitialCash);
    }
    try {
      await createAccount(payload);
      setAccountName("");
      setAccountInitialCash("");
    } catch {
      // handled by store
    }
  };

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionAccountId || !sessionName.trim()) return;
    try {
      await createSession({
        name: sessionName.trim(),
        simulator_account_id: sessionAccountId
      });
      setSessionName("");
    } catch {
      // handled by store
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      {/* Create Account */}
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<ShieldAlert size={16} />} title="创建账户" />
        <form className="grid gap-3 mt-2" onSubmit={handleCreateAccount}>
          <Input
            label="账户名"
            value={accountName}
            onChange={(e) => setAccountName(e.target.value)}
            placeholder="请输入账户名称"
          />
          <Input
            label="初始资金"
            value={accountInitialCash}
            onChange={(e) => setAccountInitialCash(e.target.value)}
            placeholder="留空使用后端默认值"
            inputMode="decimal"
          />
          <Button
            variant="primary"
            icon={<Plus size={14} />}
            type="submit"
            disabled={!accountName.trim()}
          >
            创建账户
          </Button>
        </form>
      </section>

      {/* Create Session */}
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<MessageSquare size={16} />} title="创建 Session" />
        <form className="grid gap-3 mt-2" onSubmit={handleCreateSession}>
          <Input
            label="Session 名称"
            value={sessionName}
            onChange={(e) => setSessionName(e.target.value)}
            placeholder="请输入 Session 名称"
          />
          <label className="grid gap-1.5 text-xs text-text-muted">
            账户
            <Select
              value={sessionAccountId}
              onChange={(e) => setSessionAccountId(e.target.value)}
              disabled={accounts.length === 0}
            >
              <option value="">选择账户</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </label>
          <Button
            variant="primary"
            icon={<Plus size={14} />}
            type="submit"
            disabled={!sessionAccountId || !sessionName.trim()}
          >
            创建 Session
          </Button>
        </form>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PlaceholderSection                                                */
/* ------------------------------------------------------------------ */

function PlaceholderSection({
  title,
  description
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="border border-hairline rounded-xl bg-surface-card p-4">
      <PanelHeader title={title} icon={<ShieldAlert size={16} />} />
      <EmptyState title="功能占位" description={description} />
    </section>
  );
}

function editTabDesc(tab: string): string {
  return (
    {
      余额修改: "后端尚未接入余额修改与审计接口。",
      持仓修改: "后端尚未提供持仓修改接口。",
      订单修正: "后端尚未提供订单修正接口。"
    }[tab] ?? "后端尚未提供该修改接口。"
  );
}
