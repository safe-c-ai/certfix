# certfix

[![CI](https://github.com/safe-c-ai/certfix/actions/workflows/ci.yml/badge.svg)](https://github.com/safe-c-ai/certfix/actions/workflows/ci.yml)

certfix detects CERT-C issue candidates in C code and generates reviewable
fixed-code candidates and patches with LLMs.

certfix complements static analyzers by producing repair candidates, not just
diagnostics. It can run through cloud APIs for a quick first trial, or through a
local Qwen3.6 `llama-server` route when source code must stay local.

## Run With Docker

Docker is the recommended way to try certfix.

- No local Python setup is required.
- No local compiler setup is required.
- Your source folder is mounted read-only at `/input`.
- Reports, fixed-code candidates, and patches are written to `/output`.
- Source files are not modified.

The Docker-first path is:

```text
source folder -> /input:ro -> certfix container -> /output
```

## Choose A Runtime

| Use case | Path | Sends source code to API? | Difficulty |
| --- | --- | --- | --- |
| Try certfix quickly | Docker + API check | Yes | Easy |
| Generate fix candidates quickly | Docker + API fix | Yes | Easy |
| Keep source code local | Docker Compose + local Qwen3.6 | No | Advanced |
| Develop certfix itself | pip/source install | Depends on profile | Advanced |

API mode sends source code to the configured provider. Confirm your project
data policy before using a cloud provider.

Local LLM mode keeps inference local, but still requires a GPU-capable Docker
host, NVIDIA Container Toolkit, an MTP-capable `llama-server` image, and a
Qwen3.6 GGUF model or model download access.

## Quick Start: Check With API

Prepare a source folder and an output folder:

```text
my-project/
+-- src/             # scan this folder first
`-- certfix-output/  # generated reports, fixes, and patches
```

Run `api-check` first. It writes reports and does not generate fix files.

```bash
export OPENROUTER_API_KEY=<openrouter-key>
mkdir -p certfix-output

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD/src:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:edge \
  certfix-docker api-check
```

If your C files are not under `src/`, replace `$PWD/src` with the folder you
want to scan. You can mount the project root with `$PWD:/input:ro`, but using a
smaller source folder is recommended for the first run.

### Windows PowerShell

```powershell
$env:OPENROUTER_API_KEY="<openrouter-key>"
New-Item -ItemType Directory -Force certfix-output

docker run --rm `
  -e OPENROUTER_API_KEY `
  -v "${PWD}\src:/input:ro" `
  -v "${PWD}\certfix-output:/output" `
  ghcr.io/safe-c-ai/certfix:edge `
  certfix-docker api-check
```

## Generate Fix Candidates

After checking the project, run `api-fix` to generate reviewable fixed-code
files and patches:

```bash
docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD/src:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:edge \
  certfix-docker api-fix
```

Review generated files under:

```text
certfix-output/
+-- reports/
+-- fixes/
`-- patches/
```

Generated code and patches are for manual review. Apply patches only after
reviewing them.

## What Is `certfix-docker`?

`certfix-docker` is a container helper. It generates a temporary config inside
the container, runs `certfix doctor`, then runs `certfix check` or
`certfix check` followed by `certfix fix`.

| Command | Default profile | Flow |
| --- | --- | --- |
| `certfix-docker api-check` | `deepseek-v4-flash-openrouter` | config, doctor, check |
| `certfix-docker api-fix` | `deepseek-v4-flash-openrouter` | config, doctor, check, fix |
| `certfix-docker local-check` | `qwen36-mtp-docker` | config, doctor, check |
| `certfix-docker local-fix` | `qwen36-mtp-docker` | config, doctor, check, fix |

Use a different bundled profile with `--profile`.

## What To Copy For A Separate Test Folder

When using the published certfix image with `docker run`, you do not need to
copy files from this repository. Put the C source files you want to scan in a
folder, create an output folder, and mount them as `/input` and `/output`.

```text
my-test/
+-- source/          # your .c / .h files
`-- certfix-output/  # generated reports, fixes, and patches
```

If you want to use Docker Compose instead of `docker run`, copy only the Compose
file for the route you are testing:

- API-only Compose: `docker-compose.api.yml`
- Local Qwen3.6 Compose with a self-built `llama-server` image:
  `docker-compose.local-qwen36.yml`, `docker/llama-server/Dockerfile`, and
  `docker/llama-server/entrypoint.sh`

You need a full certfix repository checkout only when building the certfix image
itself locally.

## Use A Local LLM

Use local LLM mode when source code must not be sent to an external provider.
This is an advanced path because the certfix image does not include
`llama-server`, model weights, or a GPU runtime.

With Docker Compose, certfix uses the `qwen36-mtp-docker` profile and talks to
the Compose service URL `http://llama-server:8952/v1`.

```bash
export LLAMA_SERVER_IMAGE=<mtp-capable-llama-server-image>
export SOURCE_DIR="$PWD/src"
export OUTPUT_DIR="$PWD/certfix-output"

docker compose -f docker-compose.local-qwen36.yml up -d llama-server
docker compose -f docker-compose.local-qwen36.yml run --rm certfix certfix-docker local-check
```

For the full local Qwen3.6 Compose flow, model/cache mounts, and host GPU
requirements, see [docs/DOCKER.md](docs/DOCKER.md).

## Example Output

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

LLM output is not guaranteed to be deterministic, so exact output can vary by
model, provider, prompt profile, runtime settings, and upstream model updates.
See [docs/EXAMPLE_OUTPUT.md](docs/EXAMPLE_OUTPUT.md) for a fuller walkthrough.

## Raw CLI

The Docker helper is the easiest first-run path. The underlying CLI is still
available for manual installation, development, and custom integration.

```bash
pip install certfix
certfix config deepseek-v4-flash-openrouter --output .certfix.yaml
certfix doctor
certfix check path/to/source --output-dir certfix-output
certfix fix path/to/source --output-dir certfix-output
```

| Command | First argument | Description |
| --- | --- | --- |
| `certfix config <profile>` | Profile name | Print or write a bundled config profile |
| `certfix doctor` | None | Check environment, API keys, and local server connectivity |
| `certfix check <path>` | C file or directory | Detect CERT-C issue candidates |
| `certfix fix <path>` | C file or directory | Generate fixed-code candidates and validation results |

Common options:

| Option | Commands | Description |
| --- | --- | --- |
| `--config <file>` | `doctor`, `check`, `fix`, `setup` | Use a config file other than `.certfix.yaml` |
| `--output-dir <dir>` | `check`, `fix` | Save reports, fixed-code candidates, and patches |
| `--format text\|json\|sarif` | `check`, `fix` | Select output format |
| `--force` | `config` | Overwrite an existing output file |

For compiler requirements, direct `llama-server` setup, and non-Docker examples,
see [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Model Routes And Configuration

Docker helper defaults:

- `api-check` / `api-fix`: DeepSeek V4 Flash through OpenRouter
- `local-check` / `local-fix`: local Qwen3.6 through an external
  `llama-server` service

certfix supports local, API, and hybrid model routes through `.certfix.yaml`.
Use `certfix config <profile> --output .certfix.yaml` to write a bundled
profile. For the full profile list, include paths, exclusions, advanced
routing, and token/context tuning, see
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Exit Codes

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

## Limitations

- C only. C++ is not supported.
- Supported CERT-C coverage is limited to the 115 bundled rule targets.
  CERT-C recommendations are not supported. See
  [docs/SUPPORTED_RULES.md](docs/SUPPORTED_RULES.md).
- Directory input scans `.c` / `.h` files. `certfix-output/` is skipped.
- certfix does not detect every violation, and generated fixes are not always
  correct.
- Analysis is file/function scoped, not whole-program semantic analysis.
- Repair assumes one violation per function. Multiple violations in one function
  are not supported as a single repair task.
- Functions up to about 200 lines are the expected case. Results may become less
  stable above that, and functions over about 300 lines should be split before
  running certfix.
- Header handling is limited. System headers and deep include graphs are not
  fully expanded.
- v0.2.0 fixed-code candidates are comment-stripped; comment-preserving repair
  is not implemented.
- Validation gates reduce risk but do not guarantee semantic preservation,
  security correctness, or compile success in your target build environment.
- For release test set success rates and caveats, see
  [docs/BENCHMARK_SUMMARY.md](docs/BENCHMARK_SUMMARY.md).

## Documentation

| Document | Purpose |
| --- | --- |
| [docs/INDEX.md](docs/INDEX.md) | Documentation index |
| [docs/DOCKER.md](docs/DOCKER.md) | API-only Docker and local Qwen Docker Compose usage |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Manual installation, compiler setup, and direct runtime setup |
| [docs/EXAMPLE_OUTPUT.md](docs/EXAMPLE_OUTPUT.md) | Before/after example and generated artifact walkthrough |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Config lookup, bundled profiles, include paths, advanced routing, and token/context tuning |
| [docs/SUPPORTED_RULES.md](docs/SUPPORTED_RULES.md) | Supported CERT-C rule target catalog and category coverage |
| [docs/QWEN36_MTP_RUNTIME.md](docs/QWEN36_MTP_RUNTIME.md) | Local Qwen3.6 MTP `llama-server` setup and verified runtime notes |
| [docs/BENCHMARK_SUMMARY.md](docs/BENCHMARK_SUMMARY.md) | v0.1.0 benchmark summary, release test set aggregate results, and caveats |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Release-side architecture and pipeline design |
| [docs/RESEARCH_NOTES.md](docs/RESEARCH_NOTES.md) | Boundary between public release docs and research/archive materials |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | SARIF, CERT-C metadata, and dataset boundary notices |

## AI-Assisted Development

certfix was developed with assistance from Codex and Claude Code for
implementation, review, planning, and documentation support. Proprietary LLM
outputs were not used as training targets, training-data labels, or per-record
training-data audit decisions. See [docs/RESEARCH_NOTES.md](docs/RESEARCH_NOTES.md)
for the release/research boundary.

## License

MIT. See [LICENSE](LICENSE).

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for bundled standard
fixtures and rule metadata notices.
