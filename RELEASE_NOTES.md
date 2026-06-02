# certfix Release Notes

## certfix 0.3.1

Patch release focused on Docker documentation reproducibility and release
metadata polish.

### Changes

- Updated README and Docker documentation examples to use the numbered
  `ghcr.io/safe-c-ai/certfix:0.3.1` release image tag for normal use instead of
  the moving `edge` tag.
- Clarified that `edge` follows the public `main` branch and should be used only
  when intentionally testing the latest development image.
- Restored the README limitation note that fixed-code candidates are currently
  comment-stripped.
- Adjusted benchmark documentation labels so the benchmark summary does not look
  like stale user-facing runtime guidance.

### Compatibility

- No runtime dependency changes.
- No CLI behavior changes.
- `edge` remains published for development/testing, while numbered Docker image
  tags remain the recommended user-facing route.

## certfix 0.3.0

Minor release focused on Docker-first onboarding, Docker Compose usability, and
clearer local-model runtime boundaries.

### Changes

- Reworked `README.md` around Docker-first Getting Started with API-only,
  local-only, and hybrid routes.
- Reorganized `docs/DOCKER.md` into route-based API-only, local `llama-server`,
  and hybrid Compose instructions, with reference tables and troubleshooting
  moved out of the main path.
- Changed Docker Compose defaults from fix-first to check-first:
  `docker-compose.api.yml` now defaults to `api-check`, and
  `docker-compose.local-qwen36.yml` now defaults to `local-check`.
- Updated local-only and hybrid README examples to mount an existing GGUF model
  directory explicitly with `HOST_MODEL_DIR` and `LLAMA_MODEL_PATH`.
- Documented Qwen3.6-27B MTP GPU/VRAM expectations in the Docker path.
- Clarified that the bundled detection route is verified with Qwen3.6-27B MTP,
  while repair/validation routing to other models is an advanced configuration
  path.
- Added `local-detection-deepseek-fix-docker` for Docker Compose hybrid routing
  with local Qwen3.6 detection and API-routed repair/validation.
- Clarified that `examples/input/` is available from a repository checkout, not
  from a PyPI install or a pulled Docker image alone.

### Compatibility

- The standard install remains:

```bash
pip install certfix
```

- Source files are still mounted/read as inputs and are not modified by
  certfix.
- API-only and hybrid routes still send source code to the configured provider
  for API-routed steps.
- The bundled local detection route remains Qwen3.6-27B MTP through an external
  MTP-capable `llama-server`.

## certfix 0.2.0

Minor release focused on lowering local Qwen3.6 setup friction with Docker
Compose while keeping certfix's runtime boundary explicit.

### Changes

- Added the bundled `qwen36-mtp-docker` profile for Docker Compose local Qwen3.6
  runs. The profile points certfix at `http://llama-server:8952/v1`, the service
  hostname used inside the Compose network.
- Added `local-detection-deepseek-fix-docker` for Docker Compose hybrid routing
  with local Qwen3.6 detection and DeepSeek repair/validation.
- Added `docker-compose.local-qwen36.yml` with separate `llama-server` and
  certfix services.
- Expanded `docs/DOCKER.md` with separate API-only Docker and Local Qwen3.6
  Docker Compose flows, plus the hybrid Compose route.
- Documented the remaining local Compose requirements: NVIDIA driver, NVIDIA
  Container Toolkit, GPU/VRAM capacity, model cache, and an MTP-capable
  `llama-server` image supplied through `LLAMA_SERVER_IMAGE`.
- Added release-readiness and integration-test coverage for
  `qwen36-mtp-docker` config loading, listing, and profile generation.

### Compatibility

- The standard install remains:

```bash
pip install certfix
```

- The API-only Docker image remains the easiest Docker path for users who can
  send source code to a configured provider.
- The local Qwen3.6 route still requires an external MTP-capable
  `llama-server`; certfix does not publish or bundle that server image yet.
- Source files are still not modified. Generated reports, fixed-code
  candidates, and patches are written as artifacts for manual review.

## certfix 0.1.1

Patch release focused on release polish and validation guardrail coverage.

### Changes

- Added GitHub Actions CI for linting, tests, builds, release-readiness checks,
  wheel smoke tests, and Docker image smoke tests.
- Added API-only Docker support through `Dockerfile`, `docker-compose.api.yml`,
  GHCR publishing, and `docs/DOCKER.md`.
- Added `SECURITY.md` and README example-output documentation.
- Clarified `certfix fix` output when no fixed-code candidates are generated.
- Clarified that Non-MTP `llama-server` execution is not the verified local
  profile.
- Expanded programmatic semantic-risk check tests from 2 to 22 cases, covering
  release and candidate/no-signal presets.
- Fixed two conservative programmatic check gaps:
  - `ENV33-C` now detects `exec*(..., argv)` replacements when the executable
    argument is an expression such as `argv[0]`.
  - `MEM36-C` now evaluates the `memcpy` copy-size argument instead of treating
    destination/source names as clamp evidence.

### Compatibility

- No new runtime dependency is required.
- The standard install remains:

```bash
pip install certfix
```

- The local Qwen3.6 MTP route still requires an external MTP-capable
  `llama-server`.
- API profiles still send source code to the configured provider.

## certfix 0.1.0

Initial public release for `certfix`, a CLI for detecting CERT-C issue
candidates and generating fixed-code candidates for C source code with local or
API-backed LLM runtimes.

## Highlights

- Qwen3.6-centered local workflow for detection, rule selection, fixed-code
  candidate generation, and validation.
- Release-default local profile:
  `configs/qwen36-mtp-local.yaml`.
- Bundled config profiles can be listed and written from wheel installs with
  `certfix config`.
- Candidate repair flow:
  `certfix fix <path>`.
- Validation gates for format, compile, target violation removal, semantic
  review, programmatic regression checks, and one validate-guided retry.
- Optional API profiles for users who cannot run the local model or want
  cloud-assisted repair.

## Install

```bash
pip install certfix
```

The standard install includes the lightweight OpenAI-compatible API backend used
by both cloud providers and external `llama-server` usage. The v0.1.0 public
path does not expose an in-process `llama-cpp-python` backend; local models are
used through an external OpenAI-compatible server such as `llama-server`.

## Local Runtime

The recommended local path is Qwen3.6 27B MTP through an OpenAI-compatible local
llama.cpp server:

```bash
llama-server \
  -m /path/to/qwen3.6-27b-mtp-ud-q4_k_xl.gguf \
  -ngl 99 -c 8192 -fa on -np 1 \
  --host 127.0.0.1 --port 8952 \
  --cache-ram 0 \
  --spec-type draft-mtp --spec-draft-n-max 2 \
  --reasoning-budget 1024
```

The server must support `--spec-type draft-mtp`. Builds that only expose n-gram
speculation modes are not the intended runtime for the release-default local
profile. `llama-server` is not installed by certfix; install or build a
compatible llama.cpp server separately and put it in `PATH`, or run it with an
explicit binary path.

## Quick Start

The sample commands below assume a cloned certfix repository checkout where
`examples/input/` exists. If you installed certfix from PyPI only, use your own
`.c` file or clone the repository examples.

```bash
llama-server \
  -hf unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL \
  -ngl 99 -c 8192 -fa on -np 1 \
  --host 127.0.0.1 --port 8952 \
  --cache-ram 0 \
  --spec-type draft-mtp --spec-draft-n-max 2 \
  --reasoning-budget 1024

certfix config qwen36-mtp-local --output .certfix.yaml
certfix doctor
certfix check examples/input/ --output-dir examples/certfix-output
certfix fix examples/input/ --output-dir examples/certfix-output
```

`certfix check` writes diagnostic reports under
`examples/certfix-output/reports/`. `certfix fix` writes comment-stripped
fixed-code candidates and patches under `examples/certfix-output/` without
editing source files.

## Bundled Profiles

| Profile | Use case |
| --- | --- |
| `qwen36-mtp-local` | Default local check and fix profile. |
| `qwen36-mtp-check` | Local check-only profile. |
| `deepseek-v4-flash-openrouter` | Cheap cloud-only route through OpenRouter provider routing. |
| `deepseek-v4-flash-api` | DeepSeek direct API route. |
| `gemini-3-flash-preview-openrouter` | Higher-quality API route with higher cost. |
| `local-detection-deepseek-fix` | Local Qwen3.6 detection with DeepSeek repair/validation. |
| `deepseek-gemini-step-overrides` | Advanced step-routing example. |

API routes send source code to the configured provider. Check project policy,
data residency, and vendor requirements before using cloud profiles.

## Verified Smoke

- Non-runtime release readiness checks passed:
  - public config loading;
  - bundled config resources;
  - `certfix config --list`;
  - public-surface detail scan;
  - dependency metadata;
  - wheel config packaging.
- DeepSeek direct API smoke passed on `tests/fixtures/mem30_use_after_free.c`:
  detection found `MEM30-C`, and simple fix passed compile, violation-removal,
  and semantic-review validation.
- Local Qwen3.6 MTP smoke passed on `tests/fixtures/mem30_use_after_free.c`:
  `draft-mtp` was enabled in the server log, detection found `MEM30-C`, and
  simple fix passed compile, semantic-review, and validator gates.
- Wheel install-equivalent smoke passed:
  `certfix config --list`, profile write, `doctor`, and `check`.

## Known Limitations

- C is the release target. C++ is not supported in this release.
- The tool works at file/function-oriented boundaries. Cross-translation-unit
  reasoning is limited.
- Local Qwen3.6 MTP requires a compatible llama.cpp server build and enough
  memory for the selected GGUF.
- API profiles can be useful, but they involve sending source code to external
  providers.
- Older multi-model experiments are not public install targets.
- Third-party evaluation datasets and derived split metadata are not bundled in
  the initial public package.
- Generated fixed-code candidates are written to the output directory. v0.1.0
  does not edit source files in place or provide automatic merge.
- Fixed-code candidates are comment-stripped. Comment-preserving fixed code is
  not implemented in v0.1.0.

## Release Checks

Latest local checks:

```bash
python3 -m build --sdist --wheel
python3 scripts/check_release_readiness.py
pytest -q
ruff check src/ tests/ scripts/check_release_readiness.py
git diff --check
```

At the time these notes were written, the full test suite passed with
the release maintainer checkout. Exact pass/skip counts can vary slightly by
optional local assets and dependency availability.
