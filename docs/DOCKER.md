# Docker

certfix provides an API-only Docker path for users who want to avoid setting up
a local Python environment and C compiler. This path does not include
`llama-server`, a local LLM runtime, or model weights.

API profiles send source code to the configured provider. Confirm your project
data policy before using OpenRouter, DeepSeek, or another cloud provider.

## Build The Image

From a certfix repository checkout:

```bash
docker build -t certfix:api .
```

## Run API-Only Checks

Mount the directory containing the C code at `/workspace`. The container entry
point is `certfix`, so command arguments are the same as the CLI.

```bash
export OPENROUTER_API_KEY=<openrouter-key>

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD":/workspace \
  certfix:api \
  config deepseek-v4-flash-openrouter --output .certfix.yaml --force

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD":/workspace \
  certfix:api \
  check . --output-dir certfix-output

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD":/workspace \
  certfix:api \
  fix . --output-dir certfix-output
```

Source files are not modified. Reports, fixed-code candidates, and patches are
written under `certfix-output/`.

## Docker Compose

The compose file uses the current directory as `/workspace`:

```bash
export OPENROUTER_API_KEY=<openrouter-key>

docker compose -f docker-compose.api.yml run --rm certfix \
  config deepseek-v4-flash-openrouter --output .certfix.yaml --force

docker compose -f docker-compose.api.yml run --rm certfix \
  check . --output-dir certfix-output

docker compose -f docker-compose.api.yml run --rm certfix \
  fix . --output-dir certfix-output
```

To use DeepSeek's official API profile instead, set `DEEPSEEK_API_KEY` and
generate `deepseek-v4-flash-api`.

## Local Qwen3.6 Runtime

This API-only image intentionally does not package `llama-server` or Qwen3.6
model weights. Local Qwen3.6 Docker Compose support is tracked separately
because it requires host GPU drivers, NVIDIA Container Toolkit, VRAM capacity,
and model cache management.
