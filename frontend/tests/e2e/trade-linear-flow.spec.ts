import { expect, test } from "@playwright/test";

const provider = {
  id: "provider-1",
  provider_type: "openai_compatible",
  name: "Test Provider",
  base_url: "https://example.invalid",
  api_key_masked: null,
  has_api_key: true,
  model: "test-model",
  available_models: ["test-model"],
  temperature: 0.2,
  max_tokens: null,
  timeout_seconds: 30,
  supports_tools: true,
  supports_parallel_tool_calls: false,
  supports_strict_schema: true,
  thinking_mode: null,
  strict_tool_schema: true,
  run_token_limit: null,
  created_at: "2026-05-17T00:00:00",
  updated_at: "2026-05-17T00:00:00",
};

const account = {
  id: "account-1",
  name: "测试账户",
  initial_cash: 100000,
  created_at: "2026-05-17T00:00:00",
  updated_at: "2026-05-17T00:00:00",
};

const session = {
  id: "session-1",
  name: "渐变测试会话",
  llm_account_id: "account-1",
  skill_id: null,
  prompt_role_id: null,
  simulator_account_id: "account-1",
  provider_id: "provider-1",
  model: "test-model",
  status: "idle",
  created_at: "2026-05-17T00:00:00",
  updated_at: "2026-05-17T00:00:00",
  archived_at: null,
};

const timeline = Array.from({ length: 28 }, (_, index) => ({
  type: "message",
  id: `message-${index}`,
  session_id: "session-1",
  role: index % 2 === 0 ? "user" : "assistant",
  message_type: "chat",
  content: `${index % 2 === 0 ? "用户" : "助手"}消息 ${index + 1} `.repeat(12),
  reasoning_content: index % 2 === 1 ? `推理 ${index + 1}` : null,
  created_at: `2026-05-17T00:${String(index).padStart(2, "0")}:00`,
  run_id: `run-${Math.floor(index / 2)}`,
  run_status: "finished",
  run_token_usage: index % 2 === 1 ? JSON.stringify({ total_tokens: 100 + index, latency_ms: 1000 }) : null,
  tool_call_id: null,
  tool_name: null,
  arguments_json: null,
  result_json: null,
  status: "finished",
  started_at: null,
  finished_at: null,
  error: null,
}));

test.beforeEach(async ({ page }) => {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (!path.startsWith("/api/")) return route.continue();

    if (path === "/api/providers") return route.fulfill({ json: [provider] });
    if (path === "/api/simulator/accounts") return route.fulfill({ json: [account] });
    if (path === "/api/sessions") return route.fulfill({ json: [session] });
    if (path === "/api/tools") return route.fulfill({ json: [] });
    if (path === "/api/prompt-roles") return route.fulfill({ json: [] });
    if (path === "/api/sessions/session-1/timeline") return route.fulfill({ json: timeline });
    if (path === "/api/simulator/accounts/account-1/replay-clock") {
      return route.fulfill({
        json: {
          account_id: "account-1",
          mode: "live",
          replay_time: null,
          speed: 1,
          effective_time: "2026-05-17T09:30:00",
          updated_at: "2026-05-17T09:30:00",
        },
      });
    }
    if (path === "/api/view/accounts/account-1/snapshot") {
      return route.fulfill({
        json: {
          account,
          metrics: {
            initial_cash: 100000,
            cash: 100000,
            frozen_cash: 0,
            total_asset: 100000,
            market_value: 0,
            floating_pnl: 0,
            total_pnl: 0,
            total_return_pct: 0,
            position_ratio: 0,
            position_count: 0,
            session_count: 1,
            running_sessions: 0,
          },
          positions: [],
          recent_orders: [],
          recent_trades: [],
          asset_points: [],
          sessions: [session],
        },
      });
    }

    return route.fulfill({ status: 204, body: "" });
  });
});

test("LLM Linear Flow keeps the bottom fade visible and independent of input height", async ({ page }) => {
  await page.goto("/trade");
  await page.getByText("渐变测试会话").click();
  await expect(page.getByTestId("linear-flow-shell")).toBeVisible();

  const shell = page.getByTestId("linear-flow-shell");
  const scroller = page.getByTestId("linear-flow-scroller");
  const fade = page.getByTestId("linear-flow-bottom-fade");
  const input = page.getByTestId("chat-input-surface");

  await expect(fade).toBeVisible();

  const fadeBefore = await fade.boundingBox();
  const shellBox = await shell.boundingBox();
  const scrollerBox = await scroller.boundingBox();
  const inputBefore = await input.boundingBox();
  expect(fadeBefore).not.toBeNull();
  expect(shellBox).not.toBeNull();
  expect(scrollerBox).not.toBeNull();
  expect(inputBefore).not.toBeNull();

  expect(Math.abs((fadeBefore!.y + fadeBefore!.height) - (shellBox!.y + shellBox!.height))).toBeLessThanOrEqual(1);
  expect(Math.abs(fadeBefore!.y - inputBefore!.y)).toBeLessThanOrEqual(2);
  expect(scrollerBox!.x + scrollerBox!.width).toBeGreaterThan(fadeBefore!.x + fadeBefore!.width);

  await page.getByPlaceholder("输入给 LLM 的问题。Shift + Enter 换行，Enter 发送。").focus();
  const fadeAfter = await fade.boundingBox();
  const inputAfter = await input.boundingBox();
  expect(fadeAfter).not.toBeNull();
  expect(inputAfter).not.toBeNull();

  expect(fadeAfter!.y).toBe(fadeBefore!.y);
  expect(fadeAfter!.height).toBe(fadeBefore!.height);
  expect(inputAfter!.height).toBeGreaterThan(inputBefore!.height);
});
