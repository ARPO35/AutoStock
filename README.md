# AutoStock

AutoStock is an A-share LLM simulated trading experiment system. The phase 1
MVP focuses on a single-container WebChat app with provider configuration,
tool calling, and durable local session records.

## Development

Backend:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Container:

```bash
docker build -t autostock .
docker run --rm -p 8000:8000 -v autostock-data:/app/data autostock
```

## Phase 1 MVP

Implemented surface:

- SQLite-backed provider, account, session, message, run, tool-call, and tool-result records.
- OpenAI-compatible and DeepSeek chat adapters behind one provider interface.
- `system_echo` tool for validating tool-call loops.
- Session run endpoint with per-session locking and WebSocket runtime events.
- React workbench for provider setup, account creation, session chat, tools, and runtime events.

Verification:

```bash
cd backend
python -m pytest -q
```

Frontend verification requires installing Node dependencies first:

```bash
cd frontend
npm install
npm run build
```

## Phase 2 Backend Market Data

Backend-only market data endpoints:

- `POST /api/data/fetch-history` fetches daily A-share history through AKShare and writes it to DuckDB.
- `GET /api/market/history` reads from the local cache first; pass `allow_fetch_missing=true` with `start` and `end` to fetch missing rows.
- `GET /api/market/quote` reads the latest AKShare quote and stores a quote snapshot.
- `GET /api/data/cache-status` shows cached symbol/date coverage.
- `GET /api/data/conflicts` and `POST /api/data/conflicts/{id}/resolve` expose data conflicts.

LLM tool names use OpenAI-compatible identifiers:

- `market_quote`
- `market_history`
- `data_fetch_history`

The displayed names remain `market.quote`, `market.history`, and `data.fetch_history`.

## Stage 3 Simulator Closure (A-share rules)

Implemented in backend:

- Session tool runtime now injects `session_id` and `simulator_account_id`; `order_*` and `portfolio_*` tools can bind to the current session account by default.
- Trading simulator enforces A-share baseline constraints:
  - stamp duty is sell-side only at `0.0005` (`0.5‰`);
  - T+1 sell availability is enforced with `quantity` / `available_quantity`;
  - trading-hours check is configurable and defaults enabled (`AUTOSTOCK_SIMULATOR_ENFORCE_TRADING_HOURS=1`).
- After each fill, position valuation (`market_value`, `unrealized_pnl`) and account `total_asset` are refreshed using the same valuation basis consumed by portfolio tools.
- Session timeline/message APIs expose `reasoning_content` for replay.

Backend verification used in this stage:

```bash
cd backend
python -m pytest tests/test_simulator.py tests/test_mvp.py -q
```
