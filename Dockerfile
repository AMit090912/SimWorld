# syntax=docker/dockerfile:1

FROM node:20-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    SIMWORLD_ENV=production \
    SIMWORLD_STATIC_DIR=/app/frontend/dist \
    SIMWORLD_DB_PATH=/app/data/simworld.db \
    SIMWORLD_AGENT_ALLOW_LOOPBACK=false

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=web /app/frontend/dist ./frontend/dist
COPY examples ./examples
COPY mcp_server ./mcp_server
COPY scripts ./scripts
RUN mkdir -p /app/data && useradd --create-home simworld && chown -R simworld:simworld /app
USER simworld

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["python", "-m", "uvicorn", "simworld.api.app:app", "--host", "0.0.0.0", "--port", "8000"]