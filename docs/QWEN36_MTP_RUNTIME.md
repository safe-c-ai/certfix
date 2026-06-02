# Qwen3.6 MTP Runtime

This document describes the supported local LLM runtime path for certfix.

## Supported Local Runtime

The current local profile is Qwen3.6-27B MTP through an external
OpenAI-compatible llama.cpp `llama-server`.

Use:

- model repository: `unsloth/Qwen3.6-27B-MTP-GGUF`
- recommended GGUF: `UD-Q4_K_XL`
- certfix config: `configs/qwen36-mtp-local.yaml`
- local API endpoint: `http://127.0.0.1:8952/v1`

certfix does not install `llama-server`, start it automatically, or load GGUF
files in-process. Start the server separately before running `certfix check` or
`certfix fix`.

## Why Server Mode

The MTP speedup requires llama.cpp server support for MTP speculative decoding,
including `--spec-type draft-mtp` and `--spec-draft-n-max`.

The local path is still local execution:

```text
certfix CLI
  -> http://127.0.0.1:8952/v1/chat/completions
  -> local llama.cpp llama-server
  -> local GPU/CPU inference
```

No external inference API is used by the local profile.

## Install Or Build llama-server

Use a llama.cpp build that supports `--spec-type draft-mtp`.

Verified runtime:

| Runtime | Version | Model | Notes |
| --- | --- | --- | --- |
| `am17an/llama.cpp` `mtp-clean` fork | `a957b7747` | `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL` | Verified with `--spec-type draft-mtp --spec-draft-n-max 2`. |

Other builds may work if they support Qwen3.6 MTP speculative decoding, but
they are not listed as verified release runtimes until checked.

Linux / WSL NVIDIA build example:

```bash
sudo apt update
sudo apt install -y git cmake build-essential

git clone https://github.com/am17an/llama.cpp
cd llama.cpp
git checkout a957b7747
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -t llama-server -j "$(nproc)"
```

Put the binary in `PATH`, or run it by explicit path:

```bash
sudo install -m 755 build/bin/llama-server /usr/local/bin/llama-server
llama-server --help | grep -- "--spec-type"
```

If `--spec-type` is not listed, that build is not the intended MTP runtime for
the release-default local profile.

## Start The Server

Recommended command:

```bash
llama-server \
  -hf unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL \
  -ngl 99 -c 8192 -fa on -np 1 \
  --host 127.0.0.1 --port 8952 \
  --cache-ram 0 \
  --spec-type draft-mtp --spec-draft-n-max 2 \
  --reasoning-budget 1024
```

Notes:

- `--host 127.0.0.1 --port 8952` matches the bundled certfix local profiles.
- `--cache-ram 0` avoids prompt-cache instability observed in the verified MTP
  fork during longer fix runs.
- `--reasoning-budget 1024` bounds retry reasoning when validate-guided retry is
  used.

## Model Download Behavior

With `-hf unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL`, llama.cpp downloads the
selected GGUF into its local cache on first use and reuses it later.

This requires a llama.cpp build with HTTPS download support. If the server
prints `HTTPS is not supported`, either rebuild llama.cpp with HTTPS support or
download the GGUF separately and use a local model path:

```bash
llama-server \
  -m /path/to/qwen3.6-27b-mtp-ud-q4_k_xl.gguf \
  -ngl 99 -c 8192 -fa on -np 1 \
  --host 127.0.0.1 --port 8952 \
  --cache-ram 0 \
  --spec-type draft-mtp --spec-draft-n-max 2 \
  --reasoning-budget 1024
```

## certfix Config

Write the bundled local profile:

```bash
certfix config qwen36-mtp-local --output .certfix.yaml
```

The profile uses the local server endpoint for detection, repair, and validation
roles:

```yaml
backend: local_llama_server
api:
  base_url: http://127.0.0.1:8952/v1
  model: unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL
  api_key_env: ""
```

`api_key_env: ""` intentionally disables Authorization headers for local
llama.cpp servers.

## Smoke Check

After starting `llama-server`, run:

```bash
certfix config qwen36-mtp-local --output .certfix.yaml
certfix doctor
certfix check examples/input/ --output-dir examples/certfix-output
certfix fix examples/input/ --output-dir examples/certfix-output
```

`certfix doctor` reports a warning if the local server is not reachable. Runtime
errors during `check` or `fix` return exit code 2 instead of reporting a clean
result.

## Compatibility Notes

- Builds that only expose n-gram speculation modes are not sufficient for the
  Qwen3.6 MTP GGUF family used by the release-default profile.
- If a server fails to load an MTP GGUF with a missing-tensor error such as
  `blk.64.ssm_conv1d.weight`, treat that as an incompatible runtime first.
- Non-MTP `llama-server` execution is not the verified local profile.
