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
- Session run endpoint with per-session locking, WebSocket runtime events, and handled LLM provider connection failures.
- React workbench for provider setup, account creation, session chat, tools, and runtime events.
- Session model selection now uses a full model list with implicit provider binding (no separate provider pre-selection in trade flows).

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
- `POST /api/data/fetch-minute` fetches minute A-share bars (`period`: `1/5/15/30/60`) through AKShare and writes them to DuckDB.
- `POST /api/data/fetch-announcement` fetches A-share company announcements through AKShare and writes them to DuckDB.
- `GET /api/market/history` reads from the local cache first; pass `allow_fetch_missing=true` with `start` and `end` to fetch missing rows.
- `GET /api/market/minute` reads minute bars from the local cache first; requires `symbol`, `start`, and `end`, and supports `period=1|5|15|30|60`.
- `GET /api/market/announcement` reads company announcements from the local cache first; pass `allow_fetch_missing=true` with `start` and `end` to fetch missing rows.
- `GET /api/market/quote` reads the latest AKShare quote and stores a quote snapshot.
- `GET /api/data/cache-status` shows cached symbol/date coverage.
- `GET /api/data/conflicts` and `POST /api/data/conflicts/{id}/resolve` expose data conflicts.

LLM tool names use OpenAI-compatible identifiers:

- `market_quote`
- `market_history`
- `market_minute`
- `market_announcement`
- `data_fetch_history`

The displayed names remain `market.quote`, `market.history`, `market.minute`, `market.announcement`, and `data.fetch_history`.

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

## Stage 4 Tavily Search

Implemented surface:

- `GET/PUT /api/tavily/config` stores Tavily API key and default search settings.
- `GET /api/tavily/usage` reports calls, cache hits, and estimated credits.
- LLM tools `tavily_search` and `tavily_extract` expose Tavily search and webpage extraction.
- Search/extract responses are cached in SQLite and rendered in the Chat timeline.

Environment variables:

```bash
AUTOSTOCK_TAVILY_API_KEY=
AUTOSTOCK_TAVILY_DEFAULT_SEARCH_DEPTH=basic
AUTOSTOCK_TAVILY_DEFAULT_TOPIC=finance
AUTOSTOCK_TAVILY_DEFAULT_MAX_RESULTS=5
AUTOSTOCK_TAVILY_CACHE_TTL_SECONDS=1800
```

## Trade Observation Updates

Implemented surface:

- The trade page account inspector shows account metrics, positions, recent trades, and the asset sparkline for the selected session account.
- Recent trades display stock name plus six-digit code when the backend returns `trade.name`; prices use an explicit CNY per-share format such as `100 股 @ ¥12.34/股`.
- The asset sparkline keeps the lightweight SVG implementation and adds high/mid/low y-axis labels with subtle grid lines.
- LLM provider connection errors are stored on the run, sent over the `error` WebSocket event, and returned from `POST /api/sessions/{session_id}/run` as `502 Bad Gateway` with a readable detail.
