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
docker run --rm ghcr.io/safe-c-ai/certfix:edge certfix-docker --help
```

### What Files Are Required?

For the normal published-image path, no certfix repository files are required.
Create or choose a folder containing the C source files to scan, then create an
output folder:

```text
my-test/
+-- source/          # your .c / .h files
`-- certfix-output/  # generated reports, fixed-code candidates, and patches
```

Then mount those folders:

```bash
docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD/source:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:edge \
  certfix-docker api-check
```

The files you need depend on the Docker route:

| Route | Files to copy into a separate test folder |
| --- | --- |
| Published image with `docker run` | none; only your source folder and output folder |
| API-only Compose | `docker-compose.api.yml` |
| Local Qwen Compose with an existing `llama-server` image | `docker-compose.local-qwen36.yml` |
| Local Qwen Compose with the provided `llama-server` build recipe | `docker-compose.local-qwen36.yml`, `docker/llama-server/Dockerfile`, `docker/llama-server/entrypoint.sh` |
| Build the certfix image locally | full certfix repository checkout |

The certfix image itself is pulled from GHCR for the published-image and Compose
paths. The `docker/llama-server` files are only for building your own
MTP-capable `llama-server` image; certfix does not publish one.

## Build The Image Locally

From a certfix repository checkout:

```bash
docker build -t certfix:local .
```

## Docker Mounts

The Docker-first path uses stable container paths:

| Container path | Purpose |
| --- | --- |
| `/input` | C source file or directory to scan; mount read-only when possible |
| `/output` | certfix reports, fixed-code candidates, and patches |
| `/models` | Optional local GGUF files for `llama-server` only |
| `/root/.cache` | Optional model/cache storage for `llama-server` |

The certfix container reads `/input` and writes `/output`. It does not need
direct access to local model files; local model files are for the
`llama-server` service.

## Run API-Only Check/Fix

Mount the directory containing the C code at `/input:ro` and write artifacts to
`/output`. The `certfix-docker` wrapper generates a temporary config inside the
container, runs `doctor`, and then runs `check` or `check` plus `fix`.

```bash
export OPENROUTER_API_KEY=<openrouter-key>
mkdir -p certfix-output

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:edge \
  certfix-docker api-check

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:edge \
  certfix-docker api-fix
```

Source files are not modified. Reports, fixed-code candidates, and patches are
written under the mounted output directory.

On Linux or macOS, add `--user "$(id -u):$(id -g)"` if you want generated files
owned by your host user instead of the container's default user.

Use a different bundled API profile with `--profile`:

```bash
docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:edge \
  certfix-docker api-fix --profile gemini-3-flash-preview-openrouter
```

To use DeepSeek's official API profile instead, set `DEEPSEEK_API_KEY` and use
`--profile deepseek-v4-flash-api`.

## API-Only Docker Compose

The API compose file uses `SOURCE_DIR` and `OUTPUT_DIR`. By default, it scans the
current directory and writes `./certfix-output`.

```bash
export OPENROUTER_API_KEY=<openrouter-key>
export SOURCE_DIR="$PWD"
export OUTPUT_DIR="$PWD/certfix-output"

docker compose -f docker-compose.api.yml run --rm certfix
```

Override the default command when you only want check reports:

```bash
docker compose -f docker-compose.api.yml run --rm certfix certfix-docker api-check
```

## Build A Local llama-server Image

certfix does not publish a prebuilt `llama-server` image. For local Qwen3.6
Docker Compose usage, build your own image from the provided recipe:

```bash
docker build -t certfix-llama-server:local docker/llama-server
```

The recipe builds the verified MTP-capable `am17an/llama.cpp` fork and installs
`llama-server` into the image. It does not bundle Qwen3.6 model weights.

You can override the base image or llama.cpp source at build time:

```bash
docker build \
  --build-arg BASE_IMAGE=nvidia/cuda:12.4.1-devel-ubuntu22.04 \
  --build-arg LLAMA_CPP_REPO=https://github.com/am17an/llama.cpp.git \
  --build-arg LLAMA_CPP_REF=a957b7747 \
  -t certfix-llama-server:local \
  docker/llama-server
```

## Local Qwen3.6 Docker Compose

`docker-compose.local-qwen36.yml` runs certfix beside a `llama-server` service
on the same Compose network. certfix uses the bundled `qwen36-mtp-docker`
profile and talks to `http://llama-server:8952/v1`.

This path keeps inference local, but it does not remove the GPU/runtime
requirements. You still need:

- NVIDIA driver and NVIDIA Container Toolkit on the host.
- Enough VRAM/RAM for the selected Qwen3.6 GGUF.
- An MTP-capable `llama-server` image, such as one you build from
  `docker/llama-server/Dockerfile`.
- Network access for the first model download, unless the model cache is
  already populated or you mount an existing GGUF.

Use Hugging Face download/cache:

```bash
export LLAMA_SERVER_IMAGE=certfix-llama-server:local
export SOURCE_DIR="$PWD"
export OUTPUT_DIR="$PWD/certfix-output"

docker compose -f docker-compose.local-qwen36.yml up -d llama-server
docker compose -f docker-compose.local-qwen36.yml run --rm certfix
```

Use an existing GGUF directory instead:

```bash
export LLAMA_SERVER_IMAGE=certfix-llama-server:local
export SOURCE_DIR="$PWD"
export OUTPUT_DIR="$PWD/certfix-output"
export QWEN36_MODEL_DIR=/path/to/models
export LLAMA_MODEL_PATH=/models/qwen3.6-27b-mtp-ud-q4_k_xl.gguf

docker compose -f docker-compose.local-qwen36.yml up -d llama-server
docker compose -f docker-compose.local-qwen36.yml run --rm certfix
```

Override the default certfix command when you only want check reports:

```bash
docker compose -f docker-compose.local-qwen36.yml run --rm certfix certfix-docker local-check
```

Stop the server when you are done:

```bash
docker compose -f docker-compose.local-qwen36.yml down
```

Source files are not modified. Reports, fixed-code candidates, and patches are
written under the mounted output directory.

### certfix-docker Commands

| Command | Default profile | Flow |
| --- | --- | --- |
| `certfix-docker api-check` | `deepseek-v4-flash-openrouter` | config, doctor, check |
| `certfix-docker api-fix` | `deepseek-v4-flash-openrouter` | config, doctor, check, fix |
| `certfix-docker local-check` | `qwen36-mtp-docker` | config, doctor, check |
| `certfix-docker local-fix` | `qwen36-mtp-docker` | config, doctor, check, fix |

Common options:

| Option | Default | Purpose |
| --- | --- | --- |
| `--input` | `/input` | C source file or directory |
| `--output` | `/output` | Output directory |
| `--config` | `/tmp/certfix-docker.yaml` | Temporary generated config path |
| `--profile` | command-specific | Bundled profile to generate |
| `--skip-doctor` | false | Skip diagnostics before check/fix |

### Local Compose Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLAMA_SERVER_IMAGE` | none | Required MTP-capable `llama-server` image |
| `CERTFIX_IMAGE` | `ghcr.io/safe-c-ai/certfix:edge` | certfix CLI image |
| `SOURCE_DIR` | `.` | Host source path mounted read-only at `/input` |
| `OUTPUT_DIR` | `./certfix-output` | Host output path mounted at `/output` |
| `QWEN36_MODEL_DIR` | `./models` | Host model directory mounted read-only at `/models` |
| `LLAMA_MODEL_PATH` | empty | Existing GGUF path inside the container, for example `/models/model.gguf` |
| `QWEN36_CACHE_DIR` | `qwen36-model-cache` | Named volume or host path for `/root/.cache` |
| `QWEN36_GGUF_REPO` | `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL` | Hugging Face GGUF repo/model spec passed to `llama-server -hf` |
| `LLAMA_SERVER_PORT` | `8952` | Host port mapped to the server |
| `LLAMA_N_GPU_LAYERS` | `99` | `llama-server -ngl` value |
| `LLAMA_CONTEXT_SIZE` | `8192` | `llama-server -c` value |
| `LLAMA_FLASH_ATTN` | `on` | Flash-attention setting |
| `LLAMA_PARALLEL` | `1` | `llama-server -np` value |
| `LLAMA_CACHE_RAM` | `0` | `llama-server --cache-ram` value |
| `LLAMA_SPEC_TYPE` | `draft-mtp` | Speculative decoding mode |
| `LLAMA_SPEC_DRAFT_N_MAX` | `2` | MTP draft token count |
| `LLAMA_REASONING_BUDGET` | `1024` | Server reasoning budget |
