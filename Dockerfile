FROM node:24-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AUTOSTOCK_DATA_DIR=/app/data \
    AUTOSTOCK_SQLITE_PATH=/app/data/app.db \
    AUTOSTOCK_FRONTEND_DIST_PATH=/app/frontend_dist
WORKDIR /app/backend
RUN pip install --no-cache-dir uv
COPY backend/pyproject.toml ./pyproject.toml
RUN uv pip install --system .
COPY backend/app ./app
COPY --from=frontend-build /src/frontend_dist /app/frontend_dist
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
