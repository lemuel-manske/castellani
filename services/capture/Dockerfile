FROM python:3.13.5-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.13.5-slim-bookworm

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes --no-install-recommends ca-certificates libnss3-tools && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 capture && \
    useradd --uid 10001 --gid capture --home-dir /home/capture --create-home --shell /usr/sbin/nologin capture

COPY --from=build --chown=capture:capture /app/.venv /app/.venv

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN /app/.venv/bin/playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/* && \
    chown --recursive capture:capture /ms-playwright && \
    install --directory --owner=capture --group=capture /tmp/castellani/capture

COPY --chown=capture:capture src ./src

ENV HOME=/home/capture \
    PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

USER capture

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
