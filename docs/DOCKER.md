# Docker

Docker is the recommended runtime for normal certfix use. It keeps the user
setup focused on three choices: the source folder to scan, the output folder to
write, and the model route to use.

The certfix image does not include `llama-server`, a local LLM runtime, or model
weights. API-only and hybrid profiles send source code to the configured
provider for API-routed steps. Confirm your project data policy before using
OpenRouter, DeepSeek, or another cloud provider.

## 1. Overview

### 1.1 Choose A Route

| Route | Use when | Sends source code to API? | Main requirements |
| --- | --- | --- | --- |
| A. API-only Docker | You want the easiest first run | Yes | Docker, API key |
| B. Local `llama-server` Compose | Source code must stay local | No | Docker Compose, NVIDIA GPU runtime, MTP-capable `llama-server`, GGUF model |
| C. Hybrid Compose | You want local detection with API repair/validation | Yes, for API-routed steps | Route B requirements plus API key |

### 1.2 Data And Runtime Boundaries

- Source files are mounted read-only at `/input` when possible.
- Reports, fixed-code candidates, and patches are written to `/output`.
- Source files are not modified by certfix.
- The certfix container does not need direct access to local model files.
- Local model files are used only by the `llama-server` service.

## 2. Common Setup

### 2.1 Image Tags

Use a numbered release tag for normal use. The `edge` image follows the public
`main` branch and can change after each merge.

```bash
docker pull ghcr.io/safe-c-ai/certfix:0.3.1
docker run --rm ghcr.io/safe-c-ai/certfix:0.3.1 --help
docker run --rm ghcr.io/safe-c-ai/certfix:0.3.1 certfix-docker --help
```

Tagged release images are published as `ghcr.io/safe-c-ai/certfix:<version>`
when a release tag is pushed. Use `ghcr.io/safe-c-ai/certfix:edge` only when you
intentionally want the latest public `main` branch image.

### 2.2 Input And Output Folders

Create or choose a folder containing the C source files to scan, then create an
output folder:

```text
my-project/
+-- src/             # your .c / .h files
`-- certfix-output/  # generated reports, fixed-code candidates, and patches
```

The examples below use `src/` as the input folder:

```text
/input  <-  $PWD/src
/output <-  $PWD/certfix-output
```

You can mount the project root with `$PWD:/input:ro`, but using a smaller source
folder is recommended for the first run.

### 2.3 Mounts

| Container path | Purpose |
| --- | --- |
| `/input` | C source file or directory to scan; mount read-only when possible |
| `/output` | certfix reports, fixed-code candidates, and patches |
| `/models` | Optional local GGUF files for `llama-server` only |
| `/root/.cache` | Optional model/cache storage for `llama-server` |

On Linux or macOS, add `--user "$(id -u):$(id -g)"` to `docker run` commands if
you want generated files owned by your host user instead of the container's
default user.

## 3. Route A: API-Only Docker

Use this route when you want the easiest first run and your source code can be
sent to the configured provider.

### 3.1 Check With docker run

```bash
export OPENROUTER_API_KEY=<openrouter-key>
mkdir -p certfix-output

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD/src:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:0.3.1 \
  certfix-docker api-check
```

`certfix check` returns exit code 1 when it finds issue candidates. That means
the command completed and reported findings; exit code 2 indicates usage,
configuration, model, or runtime errors.

### 3.2 Fix With docker run

Run `api-fix` after checking when you want fixed-code candidates and patches:

```bash
docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD/src:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:0.3.1 \
  certfix-docker api-fix
```

### 3.3 Use API-Only Compose

The API compose file uses the published certfix image by default. It uses
`SOURCE_DIR` and `OUTPUT_DIR`; by default, it scans the current directory and
writes `./certfix-output`.

```bash
export OPENROUTER_API_KEY=<openrouter-key>
export SOURCE_DIR="$PWD/src"
export OUTPUT_DIR="$PWD/certfix-output"

docker compose -f docker-compose.api.yml run --rm certfix
```

The Compose default command is `api-check`. Run `api-fix` explicitly when you
want fixed-code candidates and patches:

```bash
docker compose -f docker-compose.api.yml run --rm certfix certfix-docker api-fix
```

### 3.4 Use Another API Profile

Use a different bundled API profile with `--profile`:

```bash
docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD/src:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:0.3.1 \
  certfix-docker api-fix --profile gemini-3-flash-preview-openrouter
```

To use DeepSeek's official API profile instead, set `DEEPSEEK_API_KEY` and use
`--profile deepseek-v4-flash-api`.

## 4. Route B: Local `llama-server` Compose

Use this route when source code must not be sent to an external provider. This
route keeps inference local, but it does not remove the GPU/runtime
requirements.

### 4.1 Requirements

You need:

- NVIDIA driver and NVIDIA Container Toolkit on the host.
- Enough VRAM/RAM for the selected GGUF model.
- An MTP-capable `llama-server` image. The image must provide `/bin/sh` and a
  `llama-server` executable on `PATH`.
- Network access for the first model download, unless the model cache is
  already populated or you mount an existing GGUF.

The bundled `qwen36-mtp-docker` profile targets Qwen3.6-27B MTP by default.
For that default, plan for roughly 24GB VRAM + 32GB RAM minimum, with 32GB+
VRAM + 64GB RAM recommended.
The Compose route can use another compatible local model if you provide a
matching certfix config/profile and `llama-server` model settings.

### 4.2 Prepare A llama-server Image

certfix does not publish a prebuilt `llama-server` image. You can use any
MTP-capable `llama-server` image that satisfies the requirements above.

To build the provided recipe:

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

### 4.3 Choose A Model Source

Use Hugging Face download/cache:

```bash
export LLAMA_SERVER_IMAGE=certfix-llama-server:local
export SOURCE_DIR="$PWD/src"
export OUTPUT_DIR="$PWD/certfix-output"
```

Use an existing GGUF directory instead:

```bash
export LLAMA_SERVER_IMAGE=certfix-llama-server:local
export SOURCE_DIR="$PWD/src"
export OUTPUT_DIR="$PWD/certfix-output"
export HOST_MODEL_DIR=/path/to/models
export LLAMA_MODEL_PATH=/models/qwen3.6-27b-mtp-ud-q4_k_xl.gguf
```

### 4.4 Run local-check

Start `llama-server`, then run `local-check`:

```bash
docker compose -f docker-compose.local-qwen36.yml up -d llama-server
docker compose -f docker-compose.local-qwen36.yml run --rm certfix
```

The Compose default command is `local-check`.

### 4.5 Run local-fix

Run `local-fix` explicitly when you want fixed-code candidates and patches:

```bash
docker compose -f docker-compose.local-qwen36.yml run --rm certfix certfix-docker local-fix
```

### 4.6 Stop Services

```bash
docker compose -f docker-compose.local-qwen36.yml down
```

## 5. Route C: Hybrid Compose

Hybrid mode is an advanced variant of Route B. It uses the same local
`llama-server` Compose setup, but routes repair/validation through an API
provider.

### 5.1 What Is Sent To API

The bundled `local-detection-deepseek-fix-docker` profile uses the default local
Qwen3.6 detection route and an API provider for repair/validation. Source code
may be sent to the configured provider for those API-routed steps.

### 5.2 Run Hybrid Fix

```bash
export LLAMA_SERVER_IMAGE=certfix-llama-server:local
export OPENROUTER_API_KEY=<openrouter-key>
export SOURCE_DIR="$PWD/src"
export OUTPUT_DIR="$PWD/certfix-output"

docker compose -f docker-compose.local-qwen36.yml up -d llama-server
docker compose -f docker-compose.local-qwen36.yml run --rm certfix \
  certfix-docker local-fix --profile local-detection-deepseek-fix-docker
```

This uses the same `/input` and `/output` mounts as Route B, and points local
detection to `http://llama-server:8952/v1` on the Compose network.

## 6. Reference

### 6.1 Files To Copy

The files you need depend on the Docker route:

| Route | Files to copy into a separate test folder |
| --- | --- |
| Published image with `docker run` | none; only your source folder and output folder |
| API-only Compose | `docker-compose.api.yml` |
| Local `llama-server` Compose with an existing `llama-server` image | `docker-compose.local-qwen36.yml` |
| Local `llama-server` Compose with the provided `llama-server` build recipe | `docker-compose.local-qwen36.yml`, `docker/llama-server/Dockerfile`, `docker/llama-server/entrypoint.sh` |
| Hybrid Compose | Same files as Local `llama-server` Compose, plus an API key |
| Build the certfix image locally | full certfix repository checkout |

The certfix image itself is pulled from GHCR for the published-image and Compose
paths. The `docker/llama-server` files are only for building your own
MTP-capable `llama-server` image; certfix does not publish one.

### 6.2 certfix-docker Commands

| Command | Default profile | Flow |
| --- | --- | --- |
| `certfix-docker api-check` | `deepseek-v4-flash-openrouter` | config, doctor, check |
| `certfix-docker api-fix` | `deepseek-v4-flash-openrouter` | config, doctor, check, fix |
| `certfix-docker local-check` | `qwen36-mtp-docker` | config, doctor, check |
| `certfix-docker local-fix` | `qwen36-mtp-docker` | config, doctor, check, fix |

### 6.3 Common Options

| Option | Default | Purpose |
| --- | --- | --- |
| `--input` | `/input` | C source file or directory |
| `--output` | `/output` | Output directory |
| `--config` | `/tmp/certfix-docker.yaml` | Temporary generated config path |
| `--profile` | command-specific | Bundled profile to generate |
| `--skip-doctor` | false | Skip diagnostics before check/fix |

### 6.4 Compose Environment Variables

Required for all Compose routes:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CERTFIX_IMAGE` | `ghcr.io/safe-c-ai/certfix:0.3.1` | certfix CLI image |
| `SOURCE_DIR` | `.` | Host source path mounted read-only at `/input` |
| `OUTPUT_DIR` | `./certfix-output` | Host output path mounted at `/output` |

API and hybrid route variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | empty | API key forwarded to certfix for OpenRouter profiles |
| `DEEPSEEK_API_KEY` | empty | API key forwarded to certfix for DeepSeek's official API |

Local `llama-server` route variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLAMA_SERVER_IMAGE` | none | Required MTP-capable `llama-server` image |
| `HOST_MODEL_DIR` | `./models` | Host model directory mounted read-only at `/models` |
| `LLAMA_MODEL_PATH` | empty | Existing GGUF path inside the container, for example `/models/model.gguf` |
| `HOST_MODEL_CACHE_DIR` | `llama-model-cache` | Named volume or host path for `/root/.cache` |
| `LLAMA_GGUF_REPO` | `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL` | Hugging Face GGUF repo/model spec passed to `llama-server -hf` |
| `LLAMA_SERVER_PORT` | `8952` | Host port mapped to the server |

Advanced `llama-server` tuning variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLAMA_N_GPU_LAYERS` | `99` | `llama-server -ngl` value |
| `LLAMA_CONTEXT_SIZE` | `8192` | `llama-server -c` value |
| `LLAMA_FLASH_ATTN` | `on` | Flash-attention setting |
| `LLAMA_PARALLEL` | `1` | `llama-server -np` value |
| `LLAMA_CACHE_RAM` | `0` | `llama-server --cache-ram` value |
| `LLAMA_SPEC_TYPE` | `draft-mtp` | Speculative decoding mode |
| `LLAMA_SPEC_DRAFT_N_MAX` | `2` | MTP draft token count |
| `LLAMA_REASONING_BUDGET` | `1024` | Server reasoning budget |

### 6.5 Build The certfix Image Locally

Normal Docker use pulls the published certfix image. Build the certfix image
locally only when developing certfix itself:

```bash
docker build -t certfix:local .
```

## 7. Troubleshooting

### 7.1 API Key Is Missing

Set the key in your shell before running API-only or hybrid routes:

```bash
export OPENROUTER_API_KEY=<openrouter-key>
```

For DeepSeek's official API profile, use:

```bash
export DEEPSEEK_API_KEY=<deepseek-key>
```

### 7.2 Generated Files Are Owned By root

On Linux or macOS, add this to `docker run` commands:

```bash
--user "$(id -u):$(id -g)"
```

For Compose, set `OUTPUT_DIR` to a writable host directory and adjust ownership
after the run if needed.

### 7.3 certfix Cannot Connect To llama-server

Check the server logs:

```bash
docker compose -f docker-compose.local-qwen36.yml logs llama-server
```

Confirm that the server listens on port 8952 and that the Docker profile uses:

```text
http://llama-server:8952/v1
```

### 7.4 NVIDIA GPU Is Not Visible

Confirm that NVIDIA Container Toolkit is installed and Docker can see the GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```
