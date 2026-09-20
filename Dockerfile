FROM ghcr.io/astral-sh/uv:0.10.4 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY deployment/migrations ./deployment/migrations
RUN useradd --uid 10001 --create-home leasedd && mkdir -p /data/files && chown -R leasedd:leasedd /data /app
USER leasedd
ENV PATH="/app/.venv/bin:$PATH" LEASEDD_DATA_DIR=/data/files
CMD ["uvicorn","leasedd.server:app","--host","0.0.0.0","--port","8000","--no-access-log"]
