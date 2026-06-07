# certfix

[![CI](https://github.com/safe-c-ai/certfix/actions/workflows/ci.yml/badge.svg)](https://github.com/safe-c-ai/certfix/actions/workflows/ci.yml)

certfix detects CERT-C issue candidates in C code and generates reviewable
fixed-code candidates and patches with LLMs.

certfix is a route-aware LLM-assisted C repair workflow for CERT-C issue
candidates. It treats model output as reviewable fixed-code candidates, not
trusted source changes.

The goal is not to ask one model to autonomously rewrite a codebase. The goal is
to route detection, repair, validation, retry, and review work across local
models, API models, programmatic gates, and human review under real-world
constraints such as quality, cost, latency, source-code confidentiality,
reproducibility, and trust.

certfix does not modify source files in place. A `fixed` result means the
candidate passed the enabled certfix validation gates for that run; it is not a
proof of semantic correctness, security correctness, or project integration
safety.

certfix complements static analyzers by producing repair candidates, not just
diagnostics. Docker is the recommended runtime for normal use. Non-Docker
installation and direct `llama-server` operation are available for advanced or
manual use in [docs/INSTALLATION.md](docs/INSTALLATION.md).

## 1. Getting Started

certfix uses the same input/output model across API-only, local-only, and hybrid
runtime paths:

```text
source folder -> /input:ro -> certfix container -> /output
```

Source files are mounted read-only and are not modified. Reports, fixed-code
candidates, and patches are written to the output folder.

### 1.1 Prepare Folders

Create or choose a folder containing the C source files to scan, then create an
output folder:

```text
my-project/
+-- src/             # scan this folder first
`-- certfix-output/  # generated reports, fixes, and patches
```

If your C files are not under `src/`, replace `$PWD/src` in the commands below
with the folder you want to scan. You can mount the project root with
`$PWD:/input:ro`, but using a smaller source folder is recommended for the first
run.

When using the published certfix image with `docker run`, you do not need to
copy files from this repository. For Docker Compose, copy the compose file and
any supporting `llama-server` build files required for the route you are
testing; see [docs/DOCKER.md](docs/DOCKER.md).

### 1.2 Choose A Runtime

| Option | Use when | Sends source code to API? | Requirements | Start here |
| --- | --- | --- | --- | --- |
| A. API-Only | Fastest first run; source can be sent to a provider | Yes | Docker, API key | `certfix-docker api-check` |
| B. Local-Only | Source code must stay local | No | Docker Compose, NVIDIA GPU, MTP-capable `llama-server`, compatible GGUF model | `certfix-docker local-check` |
| C. Hybrid | Local detection with API repair/validation | Yes, for API-routed steps | Local-only requirements plus API key | `certfix-docker local-fix --profile local-detection-deepseek-fix-docker` |

`certfix-docker` is the Docker helper used in the commands below; see
[3.1 certfix-docker](#31-certfix-docker) for details.

API-only and hybrid modes send source code to the configured provider for the
API-routed steps. Confirm your project data policy before using either mode.

Local-only mode does not send source code to an API provider. You still need to
provide or download the model separately.

#### Option A: API-Only Mode

Use API-only mode when you want the easiest first run and your source can be
sent to the configured provider.

Run `api-check` first. It writes reports and does not generate fix files.

```bash
export OPENROUTER_API_KEY=<openrouter-key>
mkdir -p certfix-output

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD/src:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:0.4.1 \
  certfix-docker api-check
```

`certfix check` returns exit code 1 when it finds issue candidates. That means
the command completed and reported findings; exit code 2 indicates usage,
configuration, model, or runtime errors.

After checking the project, run `api-fix` to generate reviewable fixed-code
files and patches:

```bash
docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD/src:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:0.4.1 \
  certfix-docker api-fix
```

PowerShell example:

```powershell
$env:OPENROUTER_API_KEY="<openrouter-key>"
New-Item -ItemType Directory -Force certfix-output

docker run --rm `
  -e OPENROUTER_API_KEY `
  -v "$($PWD.Path)\src:/input:ro" `
  -v "$($PWD.Path)\certfix-output:/output" `
  ghcr.io/safe-c-ai/certfix:0.4.1 `
  certfix-docker api-check
```

#### Option B: Local-Only Mode

Use local-only mode when source code must not be sent to an external provider.
This is an advanced path because the certfix image does not include
`llama-server`, model weights, or a GPU runtime. The bundled Qwen3.6-27B MTP
default requires a large GPU; see [docs/DOCKER.md](docs/DOCKER.md) for runtime
requirements.

The bundled `qwen36-mtp-docker` profile targets Qwen3.6-27B MTP by default.
The Compose route can use another compatible local model if you provide a
matching certfix config/profile and `llama-server` model settings.

```bash
export LLAMA_SERVER_IMAGE=<mtp-capable-llama-server-image>
export SOURCE_DIR="$PWD/src"
export OUTPUT_DIR="$PWD/certfix-output"
export HOST_MODEL_DIR=/path/to/models
export LLAMA_MODEL_PATH=/models/qwen3.6-27b-mtp-ud-q4_k_xl.gguf

docker compose -f docker-compose.local-qwen36.yml up -d llama-server
docker compose -f docker-compose.local-qwen36.yml run --rm certfix certfix-docker local-check
```

If `LLAMA_MODEL_PATH` is not set, the compose file falls back to
`LLAMA_GGUF_REPO` and lets `llama-server` download/cache the configured GGUF.
Replace `LLAMA_MODEL_PATH` with the GGUF file you mounted under `/models`.
The bundled detection route is verified with Qwen3.6-27B MTP. Routing
repair/validation to another model is configured in
[docs/CONFIGURATION.md](docs/CONFIGURATION.md); non-MTP local runtimes require
runtime overrides described in
[docs/QWEN36_MTP_RUNTIME.md](docs/QWEN36_MTP_RUNTIME.md).

Run `local-fix` after checking when you want fixed-code candidates and patches:

```bash
docker compose -f docker-compose.local-qwen36.yml run --rm certfix certfix-docker local-fix
```

For the full local `llama-server` Compose flow, model/cache mounts, and host GPU
requirements, see [docs/DOCKER.md](docs/DOCKER.md).

#### Option C: Hybrid Mode

Hybrid mode is an advanced route. It uses the same Compose setup as
Local-Only Mode, but switches to a hybrid profile and passes an API key.

The bundled `local-detection-deepseek-fix-docker` profile uses the default local
Qwen3.6 detection route and an API provider for repair/validation. Source code
may be sent to the configured provider for those API-routed steps.

```bash
export LLAMA_SERVER_IMAGE=<mtp-capable-llama-server-image>
export OPENROUTER_API_KEY=<openrouter-key>
export SOURCE_DIR="$PWD/src"
export OUTPUT_DIR="$PWD/certfix-output"
export HOST_MODEL_DIR=/path/to/models
export LLAMA_MODEL_PATH=/models/qwen3.6-27b-mtp-ud-q4_k_xl.gguf

docker compose -f docker-compose.local-qwen36.yml up -d llama-server
docker compose -f docker-compose.local-qwen36.yml run --rm certfix \
  certfix-docker local-fix --profile local-detection-deepseek-fix-docker
```

Use the same model mount settings as Option B. If `LLAMA_MODEL_PATH` is not set,
the compose file falls back to `LLAMA_GGUF_REPO` and lets `llama-server`
download/cache the configured GGUF.

For additional routing profiles and step overrides, see
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## 2. Example Output

Given this MEM30-C use-after-free example:

```c
int run_mem30_demo(void) {
    char *p = make_message("primary", 7);
    if (p == NULL) {
        return -1;
    }

    free(p);
    print_label(p);
    return 0;
}
```

`certfix check` reports a MEM30-C issue candidate. `certfix fix` may generate a
fixed-code candidate like this:

```c
int run_mem30_demo(void) {
    char *p = make_message("primary", 7);
    if (p == NULL) {
        return -1;
    }

    print_label(p);
    free(p);
    return 0;
}
```

`certfix check` writes machine-readable reports:

```text
certfix-output/
+-- reports/
|   +-- check.json
|   +-- check.sarif
|   `-- summary.json
```

`certfix fix` adds fixed-code files and patches:

```text
certfix-output/
+-- reports/
|   +-- fixes.json
|   +-- fixes.sarif
|   `-- summary.json
+-- fixes/
|   `-- mem30_use_after_free.fixed.c
`-- patches/
    `-- mem30_use_after_free.c.patch
```

With `certfix fix --comment-merge`, certfix keeps the validated
comment-stripped artifacts above and adds conservative comment-merged review
artifacts. Add `--comment-merge-audit` when you want an LLM to reject stale or
misleading restored comments before those artifacts are written. That audit is
an explicit opt-in path that sends the source file's original comments and the
restored comments to the configured review model; do not enable it for comments
that must not be sent to an API provider.

```text
certfix-output/
+-- reports/
|   `-- comment_merge.json
+-- fixes-commented/
|   `-- mem30_use_after_free.fixed.commented.c
`-- patches-commented/
    `-- mem30_use_after_free.c.commented.patch
```

LLM output is not guaranteed to be deterministic, so exact output can vary by
model, provider, prompt profile, runtime settings, and upstream model updates.
See [docs/EXAMPLE_OUTPUT.md](docs/EXAMPLE_OUTPUT.md) for a fuller walkthrough.

## 3. CLI And Configuration

### 3.1 certfix-docker

`certfix-docker` is a container helper. It generates a temporary config inside
the container, runs `certfix doctor`, then runs `certfix check` only or
`certfix check` followed by `certfix fix`.

| Command | Default profile | Flow |
| --- | --- | --- |
| `certfix-docker api-check` | `deepseek-v4-flash-openrouter` | config, doctor, check |
| `certfix-docker api-fix` | `deepseek-v4-flash-openrouter` | config, doctor, check, fix |
| `certfix-docker local-check` | `qwen36-mtp-docker` | config, doctor, check |
| `certfix-docker local-fix` | `qwen36-mtp-docker` | config, doctor, check, fix |

Common options:

| Option | Applies to | Purpose |
| --- | --- | --- |
| `--profile <name>` | all `certfix-docker` commands | Generate a different bundled profile before running `doctor`, `check`, or `fix` |
| `--comment-merge` | `api-fix`, `local-fix` | Add conservative comment-merged review artifacts |
| `--comment-merge-audit` | `api-fix`, `local-fix` | Ask the configured review model to suppress stale or misleading restored comments before writing comment-merged artifacts |

### 3.2 Raw certfix CLI

The Docker helper is the easiest first-run path. The underlying CLI is still
available for manual installation, development, and custom integration.

```bash
pip install certfix
certfix config deepseek-v4-flash-openrouter --output .certfix.yaml
certfix doctor
certfix check path/to/source --output-dir certfix-output
certfix fix path/to/source --output-dir certfix-output
certfix fix path/to/source --output-dir certfix-output --comment-merge
certfix fix path/to/source --output-dir certfix-output --comment-merge-audit
```

For compiler requirements, direct `llama-server` setup, and non-Docker examples,
see [docs/INSTALLATION.md](docs/INSTALLATION.md).

### 3.3 Model Routes And Configuration

Docker helper defaults:

- `api-check` / `api-fix`: DeepSeek V4 Flash through OpenRouter
- `local-check` / `local-fix`: bundled default Qwen3.6 route through an
  external `llama-server` service

certfix supports local, API, and hybrid model routes through `.certfix.yaml`.
Use `certfix config <profile> --output .certfix.yaml` to write a bundled
profile. For the full profile list, include paths, exclusions, advanced
routing, and token/context tuning, see
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### 3.4 Exit Codes

`certfix check`:

| Code | Meaning |
| --- | --- |
| 0 | No issues found |
| 1 | Issues found |
| 2 | Usage, configuration, model, or runtime error |

`certfix fix`:

| Code | Meaning |
| --- | --- |
| 0 | Command completed and no failed fixes were reported |
| 1 | At least one detected issue could not be fixed or failed validation |
| 2 | Usage, configuration, model, or runtime error |

Use `certfix check` exit codes for CI violation gating.

## 4. Limitations

- C only.
- Supported CERT-C coverage is limited to the 115 bundled rule targets.
- CERT-C recommendations are not supported.
- Analysis is file/function scoped, not whole-program semantic analysis.
- Generated fixes are candidates for review, not guaranteed correct patches.
- Fixed-code candidates under `fixes/` are comment-stripped.
- `--comment-merge` can add review-only comment-merged artifacts after
  validation.
- `--comment-merge-audit` uses an LLM to suppress comment-merged artifacts when
  restored comments appear stale or misleading.
- `--comment-merge-audit` sends the source file's original comments and the
  restored comments to the configured review model and should not be used with
  API providers when comments are sensitive.
- API-only and hybrid modes may send source code to configured providers.

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for the full scope and runtime
caveats.

## 5. Documentation

| Document | Purpose |
| --- | --- |
| [docs/INDEX.md](docs/INDEX.md) | Documentation index |
| [docs/DOCKER.md](docs/DOCKER.md) | API-only, local `llama-server`, and hybrid Docker usage |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Manual installation, compiler setup, and direct runtime setup |
| [docs/FAQ.md](docs/FAQ.md) | Common questions about runtime/data boundaries, validation, model routing, human review, and benchmarks |
| [docs/EXAMPLE_OUTPUT.md](docs/EXAMPLE_OUTPUT.md) | Before/after example and generated artifact walkthrough |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Config lookup, bundled profiles, include paths, advanced routing, and token/context tuning |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | Full scope, repair, validation, and runtime limitations |
| [docs/VALIDATION_AND_RETRY.md](docs/VALIDATION_AND_RETRY.md) | Validation gates, retry behavior, and generated fix report fields |
| [docs/SUPPORTED_RULES.md](docs/SUPPORTED_RULES.md) | Supported CERT-C rule target catalog and category coverage |
| [docs/QWEN36_MTP_RUNTIME.md](docs/QWEN36_MTP_RUNTIME.md) | Local Qwen3.6 MTP `llama-server` setup and verified runtime notes |
| [docs/BENCHMARK_SUMMARY.md](docs/BENCHMARK_SUMMARY.md) | v0.1.0 release-test reference and route-selection benchmark caveats |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Release-side architecture and pipeline design |
| [docs/DESIGN_RATIONALE.md](docs/DESIGN_RATIONALE.md) | Route-aware, validation-first workflow, model routing, data boundaries, human review boundary, and model evolution |
| [docs/RESEARCH_NOTES.md](docs/RESEARCH_NOTES.md) | Boundary between public release docs and research/archive materials |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | SARIF, CERT-C, and evaluation dataset attribution and license boundaries |

## 6. License

MIT. See [LICENSE](LICENSE).

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for bundled standard
fixtures and rule metadata notices.
