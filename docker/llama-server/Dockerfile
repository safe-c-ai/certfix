# Build a local MTP-capable llama-server image for certfix Docker Compose usage.
#
# This Dockerfile is a build recipe. certfix does not publish a prebuilt
# llama-server image.

ARG BASE_IMAGE=nvidia/cuda:12.4.1-devel-ubuntu22.04
FROM ${BASE_IMAGE}

ARG LLAMA_CPP_REPO=https://github.com/am17an/llama.cpp.git
ARG LLAMA_CPP_REF=a957b7747

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN git clone "${LLAMA_CPP_REPO}" llama.cpp \
    && cd llama.cpp \
    && git checkout "${LLAMA_CPP_REF}" \
    && cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --config Release -t llama-server -j "$(nproc)" \
    && install -m 755 build/bin/llama-server /usr/local/bin/llama-server

COPY entrypoint.sh /usr/local/bin/certfix-llama-entrypoint
RUN chmod +x /usr/local/bin/certfix-llama-entrypoint

EXPOSE 8952

ENTRYPOINT ["certfix-llama-entrypoint"]
