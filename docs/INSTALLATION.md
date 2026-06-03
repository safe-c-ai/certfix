# Manual Installation

Use manual installation when you are developing certfix itself, integrating it
into an existing Python environment, or managing `llama-server` directly.

For the recommended first-run path, use Getting Started in
[README.md](../README.md#1-getting-started).

## Install

```bash
pip install certfix
```

## Requirements

- Python 3.10+
- A C compiler for compile validation, such as `gcc` or `clang`

Install a compiler first:

```bash
# Ubuntu / Debian / WSL
sudo apt update
sudo apt install build-essential

# Fedora
sudo dnf install gcc

# macOS
xcode-select --install
```

Check the environment:

```bash
gcc --version
certfix doctor
```

To use `clang`, set `validation.compile.command: clang` in `.certfix.yaml`.

## API Keys

API profiles are optional.

- OpenRouter: `OPENROUTER_API_KEY`
- DeepSeek official API: `DEEPSEEK_API_KEY`

API routes send source code to the configured provider. Confirm your project
data policy before using a cloud provider.

## Local Qwen3.6-27B Setup

For local inference, run an MTP-capable `llama-server` separately from certfix.

You need:

- MTP-capable `llama-server`
  - Verified: `am17an/llama.cpp` `mtp-clean` fork, commit `a957b7747`
  - Other builds may work if they support `--spec-type draft-mtp`
- Qwen3.6-27B MTP GGUF
  - Recommended: `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL`
- Enough RAM / VRAM for the selected GGUF
  - Rough minimum: 24GB VRAM + 32GB RAM
  - Recommended: 32GB+ VRAM + 64GB RAM
  - 16GB VRAM may require lower-bit quantization or partial offload
- Network access for the first model download, unless you already have the GGUF

Build example for Linux / WSL with NVIDIA GPU:

```bash
sudo apt update
sudo apt install -y git cmake build-essential

git clone https://github.com/am17an/llama.cpp
cd llama.cpp
git checkout a957b7747
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -t llama-server -j "$(nproc)"
```

See also:

- llama.cpp build guide:
  <https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md>
- llama-server README:
  <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>
- certfix Qwen3.6 runtime notes: [QWEN36_MTP_RUNTIME.md](QWEN36_MTP_RUNTIME.md)

Put the binary in `PATH`, or run it by explicit path:

```bash
sudo install -m 755 build/bin/llama-server /usr/local/bin/llama-server
llama-server --help | grep -- "--spec-type"
```

If `--spec-type` is not listed, that build is not the intended MTP runtime.

Start the Qwen3.6 MTP server:

```bash
llama-server \
  -hf unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL \
  -ngl 99 -c 8192 -fa on -np 1 \
  --host 127.0.0.1 --port 8952 \
  --cache-ram 0 \
  --spec-type draft-mtp --spec-draft-n-max 2 \
  --reasoning-budget 1024
```

In another terminal:

```bash
certfix config qwen36-mtp-local --output .certfix.yaml
certfix doctor
```

`certfix doctor` shows a warning and a server command example if the local
server is not reachable. certfix does not auto-start `llama-server`.

## Manual Quick Start

In a cloned certfix repository checkout, try the bundled samples in
`examples/input/`. They include a MEM30-C use-after-free example and a
multi-function file with EXP33-C / STR31-C violations.

If you installed certfix from PyPI only, `examples/input/` will not be created
in your current directory. Use your own `.c` file, or clone the repository to
run the bundled examples.

The commands below write results to `examples/certfix-output`. Source files are
not modified. `certfix check` writes reports, and `certfix fix` writes
comment-stripped fixed-code candidates under `fixes/` plus patches under
`patches/`. Add `--comment-merge` to `certfix fix` when you also want
review-only comment-merged artifacts, or `--comment-merge-audit` when you want
an LLM to audit restored comments before writing those artifacts. The audit
sends the source file's original comments and the restored comments to the
configured review model.

### API Only

No local GPU or `llama-server` is required.

OpenRouter with DeepSeek V4 Flash:

```bash
export OPENROUTER_API_KEY=<openrouter-key>
certfix config deepseek-v4-flash-openrouter --output .certfix.yaml
certfix check examples/input/ --output-dir examples/certfix-output
certfix fix examples/input/ --output-dir examples/certfix-output
```

OpenRouter with Gemini 3 Flash Preview:

```bash
export OPENROUTER_API_KEY=<openrouter-key>
certfix config gemini-3-flash-preview-openrouter --output .certfix.yaml
certfix check examples/input/ --output-dir examples/certfix-output
certfix fix examples/input/ --output-dir examples/certfix-output
```

### Local Qwen3.6-27B Only

Start `llama-server` first, then run:

```bash
certfix config qwen36-mtp-local --output .certfix.yaml
certfix doctor
certfix check examples/input/ --output-dir examples/certfix-output
certfix fix examples/input/ --output-dir examples/certfix-output
```

This path keeps inference local and does not send code to a cloud API.

For Docker Compose, use the `qwen36-mtp-docker` profile instead. It points
certfix at the Compose service URL `http://llama-server:8952/v1` rather than
`127.0.0.1`.

See [DOCKER.md](DOCKER.md) for the full local Compose flow, including
`local-check`, `local-fix`, model/cache mounts, and host GPU/runtime
requirements.

### API And Local Combined

This profile uses local Qwen3.6-27B for detection and DeepSeek V4 Flash for
repair/validation. It requires both `OPENROUTER_API_KEY` and a running
`llama-server`.

```bash
export OPENROUTER_API_KEY=<openrouter-key>
certfix config local-detection-deepseek-fix --output .certfix.yaml
certfix doctor
certfix check examples/input/ --output-dir examples/certfix-output
certfix fix examples/input/ --output-dir examples/certfix-output
```
