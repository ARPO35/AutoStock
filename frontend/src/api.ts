export type ProviderType = "openai_compatible" | "deepseek";

export interface Provider {
  id: string;
  provider_type: ProviderType;
  name: string;
  base_url: string;
  api_key_masked: string | null;
  has_api_key: boolean;
  model: string;
  temperature: number;
  max_tokens: number | null;
  timeout_seconds: number;
  supports_tools: boolean;
  supports_parallel_tool_calls: boolean;
  supports_strict_schema: boolean;
  thinking_mode: string | null;
  strict_tool_schema: boolean;
  created_at: string;
  updated_at: string;
}

export interface Account {
  id: string;
  name: string;
  provider_id: string;
  initial_cash: number;
  created_at: string;
  updated_at: string;
}

export interface Session {
  id: string;
  name: string;
  llm_account_id: string | null;
  skill_id: string | null;
  simulator_account_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface Message {
  id: string;
  session_id: string;
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  message_type: string;
  trigger_id: string | null;
  parent_message_id: string | null;
  created_at: string;
}

export interface ToolSchema {
  name: string;
  display_name: string;
  description: string;
  parameters: Record<string, unknown>;
  strict: boolean;
}

export interface RuntimeEvent {
  type: string;
  session_id: string;
  run_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  arguments_json?: string;
  ok?: boolean;
  result?: Record<string, unknown> | null;
  error?: string | null;
  status?: string;
  message?: Message;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status text when the server did not return JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  providers: () => request<Provider[]>("/api/providers"),
  createProvider: (payload: Record<string, unknown>) =>
    request<Provider>("/api/providers", { method: "POST", body: JSON.stringify(payload) }),
  accounts: () => request<Account[]>("/api/accounts"),
  createAccount: (payload: Record<string, unknown>) =>
    request<Account>("/api/accounts", { method: "POST", body: JSON.stringify(payload) }),
  sessions: () => request<Session[]>("/api/sessions"),
  createSession: (payload: Record<string, unknown>) =>
    request<Session>("/api/sessions", { method: "POST", body: JSON.stringify(payload) }),
  messages: (sessionId: string) => request<Message[]>(`/api/sessions/${sessionId}/messages`),
  runSession: (sessionId: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/sessions/${sessionId}/run`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  tools: () => request<ToolSchema[]>("/api/tools")
};
