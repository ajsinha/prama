# Prama — the all-in-one image (W10.7).
# Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
#
# One container that serves the console and the API against SQLite, so an
# evaluation needs a single `docker run` and no cluster. It is deliberately not
# the production shape: a control plane holding its own database inside its own
# container has nowhere to fail over to, and `deploy/README.md` says so.
#
# Two properties this Dockerfile has that a hand-rolled one usually does not:
#
#   * The interpreter is pinned to the same 3.13 the project pins, so an image
#     cannot be built on a Python the test suite has never run on.
#   * It runs as a non-root user. A control plane that reads a bank's data as
#     root fails the first container review, and adding the user afterwards
#     means every volume mount has the wrong ownership.

FROM python:3.13-slim AS build

# Build in a virtual environment so the runtime layer copies one directory and
# inherits no build tooling — a compiler in a production image is a finding.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
COPY schema ./schema
RUN pip install --no-cache-dir ".[serve]"

FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="Prama" \
      org.opencontainers.image.description="Business-owned, evidence-first data quality control plane" \
      org.opencontainers.image.vendor="Ashutosh Sinha" \
      org.opencontainers.image.licenses="Proprietary"

# The schema files are the authority and there are no migrations, so they ship
# with the image rather than being fetched: an image whose schema came from
# somewhere else is an image whose database nobody can verify.
COPY --from=build /opt/venv /opt/venv
COPY schema /opt/prama/schema
COPY config/application.yaml /opt/prama/config/application.yaml

ENV PATH="/opt/venv/bin:$PATH" \
    PRAMA_DATABASE__SCHEMA_DIR=/opt/prama/schema \
    PRAMA_DATABASE__SQLITE__PATH=/data/prama.db \
    PRAMA_WEB__ENABLED=true

# Non-root, and the data directory is owned before the volume is declared so a
# fresh volume inherits the right ownership rather than root's.
RUN useradd --system --uid 10001 --home /opt/prama prama \
    && mkdir -p /data \
    && chown -R prama:prama /data /opt/prama
USER prama
VOLUME ["/data"]
WORKDIR /opt/prama

EXPOSE 8080

# No default secret. The image refuses to start without one, exactly as a
# source checkout does — an image that generated its own would mean every
# deployment that never read the documentation runs on a key baked into a
# public layer.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=2).status==200 else 1)"

ENTRYPOINT ["prama"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
