FROM nvcr.io/nvidia/tensorrt:23.10-py3

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    libssl-dev \
    zlib1g-dev \
    libzip-dev \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q https://github.com/Kitware/CMake/releases/download/v3.21.3/cmake-3.21.3-linux-x86_64.sh -O /tmp/cmake-install.sh \
    && chmod +x /tmp/cmake-install.sh \
    && /tmp/cmake-install.sh --skip-license --prefix=/usr/local \
    && rm /tmp/cmake-install.sh

RUN git clone --branch stable https://github.com/lightvector/KataGo.git /KataGo
WORKDIR /KataGo/cpp
RUN cmake . -DUSE_BACKEND=TENSORRT && make -j$(nproc)
RUN ln -s /KataGo/cpp/katago /usr/local/bin/katago

WORKDIR /app
COPY pyproject.toml ./
COPY katago_server/ katago_server/
COPY config/ config/

RUN python -m pip install --no-cache-dir .

ENV KATAGO_KATAGO_BINARY=katago \
    KATAGO_ANALYSIS_CONFIG=/app/config/analysis.cfg \
    KATAGO_MODEL_PATH=/app/models/default.bin.gz \
    KATAGO_HOST=0.0.0.0 \
    KATAGO_PORT=8000

EXPOSE 8000

CMD ["katago-server", "serve"]
