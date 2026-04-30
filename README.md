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
