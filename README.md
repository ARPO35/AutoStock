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
