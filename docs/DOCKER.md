# Docker

certfix provides two Docker paths:

- API-only Docker for users who want to avoid setting up a local Python
  environment and C compiler.
- Local Qwen3.6 Docker Compose for users who already have a GPU-capable Docker
  host and an MTP-capable `llama-server` image.

The certfix image does not include `llama-server`, a local LLM runtime, or model
weights. API profiles send source code to the configured provider. Confirm your
project data policy before using OpenRouter, DeepSeek, or another cloud
provider.

## Use The Published Image

The `edge` image follows the public `main` branch. Tagged release images are
published as `ghcr.io/safe-c-ai/certfix:<version>` when a release tag is pushed.

```bash
docker pull ghcr.io/safe-c-ai/certfix:edge
docker run --rm ghcr.io/safe-c-ai/certfix:edge --help
```

## Build The Image Locally

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
  ghcr.io/safe-c-ai/certfix:edge \
  config deepseek-v4-flash-openrouter --output .certfix.yaml --force

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD":/workspace \
  ghcr.io/safe-c-ai/certfix:edge \
  check . --output-dir certfix-output

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD":/workspace \
  ghcr.io/safe-c-ai/certfix:edge \
  fix . --output-dir certfix-output
```

Source files are not modified. Reports, fixed-code candidates, and patches are
written under `certfix-output/`.

## API-Only Docker Compose

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

## Local Qwen3.6 Docker Compose

`docker-compose.local-qwen36.yml` runs certfix beside a `llama-server` service
on the same Compose network. Inside Compose, certfix must use
`http://llama-server:8952/v1` instead of `http://127.0.0.1:8952/v1`, so this
path uses the bundled `qwen36-mtp-docker` profile.

This path keeps inference local, but it does not remove the GPU/runtime
requirements. You still need:

- NVIDIA driver and NVIDIA Container Toolkit on the host.
- Enough VRAM/RAM for the selected Qwen3.6 GGUF.
- An MTP-capable `llama-server` container image that provides a `llama-server`
  binary and supports `--spec-type draft-mtp`.
- Network access for the first model download, unless the model cache is
  already populated.

certfix does not publish the `llama-server` image yet. Set
`LLAMA_SERVER_IMAGE` to an image you have built or trust:

```bash
export LLAMA_SERVER_IMAGE=<mtp-capable-llama-server-image>
```

Start the local server:

```bash
docker compose -f docker-compose.local-qwen36.yml up -d llama-server
```

Generate the Docker-specific profile and run diagnostics:

```bash
docker compose -f docker-compose.local-qwen36.yml run --rm certfix \
  config qwen36-mtp-docker --output .certfix.yaml --force

docker compose -f docker-compose.local-qwen36.yml run --rm certfix doctor
```

Run check/fix on the mounted project:

```bash
docker compose -f docker-compose.local-qwen36.yml run --rm certfix \
  check . --output-dir certfix-output

docker compose -f docker-compose.local-qwen36.yml run --rm certfix \
  fix . --output-dir certfix-output
```

Stop the server when you are done:

```bash
docker compose -f docker-compose.local-qwen36.yml down
```

Source files are not modified. Reports, fixed-code candidates, and patches are
written under `certfix-output/`.

### Local Compose Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLAMA_SERVER_IMAGE` | none | Required MTP-capable `llama-server` image |
| `CERTFIX_IMAGE` | `ghcr.io/safe-c-ai/certfix:edge` | certfix CLI image |
| `QWEN36_GGUF_REPO` | `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL` | Hugging Face GGUF repo/model spec passed to `llama-server -hf` |
| `LLAMA_SERVER_PORT` | `8952` | Host port mapped to the server |
| `LLAMA_N_GPU_LAYERS` | `99` | `llama-server -ngl` value |
| `LLAMA_CONTEXT_SIZE` | `8192` | `llama-server -c` value |
| `LLAMA_SPEC_DRAFT_N_MAX` | `2` | MTP draft token count |
| `LLAMA_REASONING_BUDGET` | `1024` | Server reasoning budget |
