# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

# Python 3.12.13 slim Bookworm multi-architecture manifest.
ARG PYTHON_BASE_IMAGE=python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

FROM ${PYTHON_BASE_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build locked dependencies in their own cacheable layer. Application source
# changes then rebuild only the small project wheel.
COPY requirements.lock ./
RUN python -m pip wheel --wheel-dir /wheels --requirement requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --no-deps --wheel-dir /wheels .


FROM ${PYTHON_BASE_IMAGE} AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

LABEL org.opencontainers.image.title="Property Intelligence Engine" \
      org.opencontainers.image.description="AI-assisted short-term rental listing analysis API" \
      org.opencontainers.image.source="https://github.com/Miguesh/Property-Intelligence-Engine"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --no-log-init --create-home \
        --home-dir /home/app --shell /usr/sbin/nologin app

COPY --from=builder /build/requirements.lock /requirements.lock
COPY --from=builder /wheels /wheels

RUN python -m pip install --no-index --find-links=/wheels --no-deps \
        --requirement /requirements.lock \
    && python -m pip install --no-index --find-links=/wheels --no-deps \
        property-intelligence-engine \
    && rm -rf /requirements.lock /wheels

WORKDIR /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).close()"]

CMD ["uvicorn", "property_intelligence.bootstrap:app", "--host", "0.0.0.0", "--port", "8000"]
