FROM debian:bookworm-20260824-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171 AS katago-build

ARG KATAGO_VERSION=1.16.4
ARG KATAGO_SOURCE_SHA256=51b1a9b48053b0de910f44abf2cc95160de7b6d43bb22300e0b80ea0b3ed0ca8
ARG KATAGO_MODEL_URL=https://media.katagotraining.org/uploaded/networks/models/kata1/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz
ARG KATAGO_MODEL_SHA256=9d7a6afed8ff5b74894727e156f04f0cd36060a24824892008fbb6e0cba51f1d

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates cmake curl g++ libeigen3-dev libzip-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN curl -L --fail --retry 3 --output /tmp/katago.tar.gz \
        "https://github.com/lightvector/KataGo/archive/refs/tags/v${KATAGO_VERSION}.tar.gz" \
    && echo "${KATAGO_SOURCE_SHA256}  /tmp/katago.tar.gz" | sha256sum --check --strict \
    && mkdir /src \
    && tar -xzf /tmp/katago.tar.gz --strip-components=1 -C /src
RUN cmake -S /src/cpp -B /src/build \
        -DNO_GIT_REVISION=1 -DUSE_BACKEND=EIGEN \
        -DEIGEN3_INCLUDE_DIRS=/usr/include/eigen3 -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /src/build --target katago --parallel 2
RUN curl -L --fail --retry 3 --output /tmp/model.bin.gz "${KATAGO_MODEL_URL}" \
    && echo "${KATAGO_MODEL_SHA256}  /tmp/model.bin.gz" | sha256sum --check --strict
RUN mkdir -p /licenses/katago \
    && cp /src/LICENSE /licenses/katago/LICENSE \
    && find /src/cpp/external -type f \( -iname 'license*' -o -iname 'copying*' \) \
        -exec cp --parents '{}' /licenses/katago \;

FROM python:3.14.7-slim-bookworm@sha256:416f0db2a2b561945630cef9877a7ea0581b27449eb9fd9df42f03e1b74b5b63

ARG VCS_REF=unreleased
LABEL org.opencontainers.image.source="https://github.com/yulinhenryou/go-review-ai" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GO_REVIEW_PUBLIC=1 \
    GO_REVIEW_RELEASE=${VCS_REF} \
    GO_REVIEW_CLIENT_IP_HEADER=fly-client-ip \
    GO_REVIEW_ALLOWED_ORIGINS=[] \
    GO_REVIEW_QUEUE_CAPACITY=1 \
    GO_REVIEW_JOB_TIMEOUT=900 \
    GO_REVIEW_RESULT_TTL=900 \
    GO_REVIEW_RATE_WINDOW=3600 \
    GO_REVIEW_CLIENT_LIMIT=4 \
    GO_REVIEW_GLOBAL_LIMIT=20 \
    KATAGO_PATH=/opt/katago/katago \
    KATAGO_MODEL_PATH=/opt/katago/model.bin.gz \
    KATAGO_CONFIG_PATH=/app/config/deployment-eigen.cfg \
    KATAGO_MAX_VISITS=64

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 libzip4 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

WORKDIR /app
COPY pyproject.toml constraints.txt ./
COPY app ./app
COPY src ./src
RUN python -m pip install --no-cache-dir --constraint constraints.txt '.[api]'
COPY frontend ./frontend
COPY config/deployment-eigen.cfg ./config/deployment-eigen.cfg
COPY scripts/container_server.py ./scripts/container_server.py
COPY licenses/KATAGO_NETWORK_LICENSE.txt /licenses/KATAGO_NETWORK_LICENSE.txt
COPY --from=katago-build /src/build/katago /opt/katago/katago
COPY --from=katago-build /tmp/model.bin.gz /opt/katago/model.bin.gz
COPY --from=katago-build /licenses/katago /licenses/katago

RUN /opt/katago/katago version \
    && chown -R app:app /app /opt/katago
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5m --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"]
CMD ["python", "scripts/container_server.py"]
