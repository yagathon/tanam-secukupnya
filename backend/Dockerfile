# Cloud Run image. Build from the repo root (the seed data lives outside backend/):
#   docker build -f backend/Dockerfile -t tanam-api .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY data/seed /srv/data/seed
ENV PORT=8080 PATH="/srv/backend/.venv/bin:$PATH"
CMD exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
