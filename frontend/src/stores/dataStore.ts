import { create } from "zustand";
import type { Provider, Account, Session, ToolSchema, PromptRole } from "@/api";
import { api } from "@/api";

interface DataState {
  providers: Provider[];
  accounts: Account[];
  sessions: Session[];
  tools: ToolSchema[];
  promptRoles: PromptRole[];

  loadAll: () => Promise<void>;
  loadSessions: () => Promise<void>;
  loadPromptRoles: () => Promise<void>;
  refreshAll: () => Promise<void>;

  createProvider: (payload: Record<string, unknown>) => Promise<Provider>;
  createAccount: (payload: Record<string, unknown>) => Promise<Account>;
  createSession: (payload: Record<string, unknown>) => Promise<Session>;

  updateProvider: (id: string, payload: Record<string, unknown>) => Promise<Provider>;
  deleteProvider: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
}

export const useDataStore = create<DataState>((set, get) => ({
  providers: [],
  accounts: [],
  sessions: [],
  tools: [],
  promptRoles: [],

  loadAll: async () => {
    try {
      const [p, a, s, t, promptRoles] = await Promise.all([
        api.providers(),
        api.accounts(),
        api.sessions(),
        api.tools(),
        api.promptRoles()
      ]);
      set({ providers: p, accounts: a, sessions: s, tools: t, promptRoles });
    } catch {
      // handled by ui store error
    }
  },

  loadSessions: async () => {
    try {
      set({ sessions: await api.sessions() });
    } catch {
      // handled by ui store
    }
  },

  loadPromptRoles: async () => {
    try {
      set({ promptRoles: await api.promptRoles() });
    } catch {
      // handled by ui store
    }
  },

  refreshAll: async () => {
    await get().loadAll();
  },

  createProvider: async (payload) => {
    const created = await api.createProvider(payload);
    set((s) => ({ providers: [created, ...s.providers] }));
    return created;
  },

  createAccount: async (payload) => {
    const created = await api.createAccount(payload);
    set((s) => ({ accounts: [created, ...s.accounts] }));
    return created;
  },

  createSession: async (payload) => {
    const promptRoleId = payload.prompt_role_id ?? get().promptRoles[0]?.id;
    const created = await api.createSession({
      ...payload,
      ...(promptRoleId ? { prompt_role_id: promptRoleId } : {})
    });
    set((s) => ({ sessions: [created, ...s.sessions] }));
    return created;
  },

  updateProvider: async (id, payload) => {
    const updated = await api.updateProvider(id, payload);
    set((s) => ({
      providers: s.providers.map((p) => (p.id === id ? updated : p))
    }));
    return updated;
  },

  deleteProvider: async (id) => {
    await api.deleteProvider(id);
    set((s) => ({ providers: s.providers.filter((p) => p.id !== id) }));
  },

  deleteSession: async (id) => {
    await api.deleteSession(id);
    set((s) => ({ sessions: s.sessions.filter((s) => s.id !== id) }));
  }
}));
