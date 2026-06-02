# certfix

[![CI](https://github.com/safe-c-ai/certfix/actions/workflows/ci.yml/badge.svg)](https://github.com/safe-c-ai/certfix/actions/workflows/ci.yml)

certfix is a CLI tool for detecting CERT-C issue candidates and generating
fixed-code candidates for C source code with LLMs.

## Features

- Detect CERT-C security violation candidates in C source code
- Use a bundled catalog of 115 CERT-C rule targets across PRE, DCL, EXP, INT,
  FLP, ARR, STR, MEM, FIO, ENV, SIG, ERR, CON, MSC, and POS categories
- Write AI-generated fixed-code candidates and patches
- Run the standard local path with Qwen3.6 MTP through `llama-server`
- Use local servers and cloud APIs through OpenAI-compatible API backends
  - v0.2.0 ships profiles for local `llama-server` with Qwen3.6-27B,
    OpenRouter with DeepSeek V4 Flash / Gemini 3 Flash Preview, and DeepSeek's
    official API with DeepSeek V4 Flash
- Reduce risk with compile validation, violation-removal checks, and semantic
  review gates
- Produce machine-readable JSON / SARIF output and exit codes

## Quick Start With Docker

Docker is the recommended first-run path because the image includes Python,
certfix, and the compiler tools needed for validation. Source files are mounted
read-only at `/input`, and reports, fixed-code candidates, and patches are
written to `/output`.

API routes send source code to the configured provider. Confirm your project
data policy before using a cloud provider.

```bash
export OPENROUTER_API_KEY=<openrouter-key>
mkdir -p certfix-output

docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:edge \
  certfix-docker api-fix
```

This generates a temporary Docker config inside the container, runs `doctor`,
then runs `check` followed by `fix`. Source files are not modified.

Use `api-check` instead of `api-fix` when you only want reports:

```bash
docker run --rm \
  -e OPENROUTER_API_KEY \
  -v "$PWD:/input:ro" \
  -v "$PWD/certfix-output:/output" \
  ghcr.io/safe-c-ai/certfix:edge \
  certfix-docker api-check
```

For Docker Compose, local Qwen3.6, model/cache mounts, and Linux user-id
options, see [docs/DOCKER.md](docs/DOCKER.md).

### What To Copy For A Separate Test Folder

When using the published certfix image with `docker run`, you do not need to
copy files from the certfix repository. Put the C source files you want to scan
in a folder, create an output folder, and mount them as `/input` and `/output`.

```text
my-test/
+-- source/          # your .c / .h files
`-- certfix-output/  # generated reports, fixed-code candidates, and patches
```

If you want to use Docker Compose instead of `docker run`, copy only the Compose
file for the route you are testing:

- API-only Compose: `docker-compose.api.yml`
- Local Qwen3.6 Compose with a self-built `llama-server` image:
  `docker-compose.local-qwen36.yml`, `docker/llama-server/Dockerfile`, and
  `docker/llama-server/entrypoint.sh`

You need a full certfix repository checkout only when building the certfix image
itself locally.

## Manual Installation

Manual installation is available for development, existing Python
environments, and users who want to manage `llama-server` directly.

```bash
pip install certfix
```

For compiler requirements, API profile setup, local Qwen3.6 `llama-server`
setup, and non-Docker examples, see [docs/INSTALLATION.md](docs/INSTALLATION.md).

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

LLM output is not guaranteed to be deterministic, so exact fixed-code candidates
can vary by model, provider, prompt profile, and runtime settings. Review the
generated patch before applying it. See
[docs/EXAMPLE_OUTPUT.md](docs/EXAMPLE_OUTPUT.md) for a fuller walkthrough.

For `certfix check`, the output directory contains machine-readable reports:

```text
examples/certfix-output/
+-- reports/
|   +-- check.json
|   +-- check.sarif
|   `-- summary.json
```

For `certfix fix`, certfix writes reviewable fixed-code candidates and patches
without editing the original source files:

```text
examples/certfix-output/
+-- reports/
|   +-- fixes.json
|   +-- fixes.sarif
|   `-- summary.json
+-- fixes/
|   `-- mem30_use_after_free.fixed.c
`-- patches/
    `-- mem30_use_after_free.c.patch
```

Paths vary by input file and function name. Treat generated code and patches as
candidates for manual review, not as automatic source changes.

## Commands

Basic flow:

1. Create `.certfix.yaml` in the directory where you run certfix.
2. Run `certfix doctor` to check the environment, API keys, and local server.
3. Run `certfix check <path>` to detect CERT-C violation candidates.
4. Run `certfix fix <path>` to generate repair candidates and validation
   results.
5. Review `certfix-output/` fixed-code candidates and patches, then merge
   changes manually if appropriate.

| Command | First argument | Description |
|---------|----------------|-------------|
| `certfix config <profile>` | Profile name | Print or write a bundled config profile |
| `certfix doctor` | None | Check environment, API keys, and local server connectivity |
| `certfix check <path>` | C file or directory | Detect CERT-C violation candidates |
| `certfix fix <path>` | C file or directory | Generate repair candidates and validation results without editing source files |

Common options:

| Option | Commands | Description |
|--------|----------|-------------|
| `--config <file>` | `doctor`, `check`, `fix`, `setup` | Use a config file other than `.certfix.yaml` |
| `--output-dir <dir>` | `check`, `fix` | Save reports, comment-stripped fixed-code candidates, and patches |
| `--format text\|json\|sarif` | `check`, `fix` | Select output format |
| `--force` | `config` | Overwrite an existing output file |

Use `certfix --help` or `certfix <command> --help` for the full CLI reference.

`certfix setup` shows optional model-file diagnostics. It is not required for
the normal API or external `llama-server` paths.

## Model Profiles

certfix writes bundled profiles to `.certfix.yaml`. Without `--config`, certfix
reads `.certfix.yaml` from the current working directory.

```bash
certfix config qwen36-mtp-local --output .certfix.yaml
```

A local Qwen3.6 profile contains connection details like:

```yaml
detection:
  backend: local_llama_server
  prompt_profile: qwen36_certfix_check_v1
  batch_size: 1
  api:
    base_url: http://127.0.0.1:8952/v1
    model: unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL
    api_key_env: ""
```

For API providers, put keys in your shell environment or in a local `.env` file.
Existing shell environment variables take precedence over `.env`.

```dotenv
OPENROUTER_API_KEY=<openrouter-key>
DEEPSEEK_API_KEY=<deepseek-key>
```

Bundled profiles:

| Purpose | Profile | Notes |
|---------|---------|-------|
| Local standard | `qwen36-mtp-local` | Local Qwen3.6-27B MTP for detection and repair |
| Local Docker Compose | `qwen36-mtp-docker` | Local Qwen3.6-27B MTP through the Compose `llama-server` service |
| Local check only | `qwen36-mtp-check` | Detection without repair |
| API only: DeepSeek | `deepseek-v4-flash-openrouter` | DeepSeek V4 Flash through OpenRouter |
| API only: Gemini | `gemini-3-flash-preview-openrouter` | Gemini 3 Flash Preview through OpenRouter |
| API only: DeepSeek direct | `deepseek-v4-flash-api` | DeepSeek official API |
| Local detection + API repair | `local-detection-deepseek-fix` | Qwen3.6-27B detection with DeepSeek repair/validation |
| Advanced routing | `deepseek-gemini-step-overrides` | Example for routing selected steps to different models |

Repair-quality guideline from the v0.1.0 CERT-C repair release test set:

```text
Qwen3.6-27B local < DeepSeek V4 Flash < Gemini 3 Flash Preview
```

See [docs/BENCHMARK_SUMMARY.md](docs/BENCHMARK_SUMMARY.md) for benchmark
context and caveats.

Selection guideline:

- Use `qwen36-mtp-local` when you have a local GPU and do not want to send code
  to an external API.
- Use `qwen36-mtp-docker` when certfix runs in Docker Compose beside a
  `llama-server` service.
- Use `deepseek-v4-flash-openrouter` when you do not have a local GPU and want a
  lower-cost API route.
- Use `local-detection-deepseek-fix` when you have local Qwen3.6 detection but
  want low-cost API repair.
- Use `gemini-3-flash-preview-openrouter` when API repair quality matters more
  than cost.

API routes send source code to the configured provider. Local Qwen3.6 profiles
use an external MTP-capable `llama-server`; certfix does not load GGUF files
in-process.

## Configuration

certfix reads `.certfix.yaml` to choose the model route, API provider,
validation gates, and project-specific exclusions.

Config lookup:

- With `--config <file>`: certfix reads the specified file.
- Without `--config`: certfix reads `.certfix.yaml` in the current working
  directory.

If `.certfix.yaml` is missing, built-in defaults are incomplete for public use.
Create a profile first with `certfix config <profile> --output .certfix.yaml`.

Common project-specific edits:

```yaml
check:
  exclude:
    - "tests/"
    - "vendor/"

validation:
  compile:
    command: gcc
    args: ["-fsyntax-only"]
    include_paths:
      - "include/"
```

- `check.exclude`: files or directories to skip
- `validation.compile.command`: C compiler for compile validation
- `validation.compile.include_paths`: project header search paths for compiler
  validation

For header context used by analysis prompts, advanced routing, token tuning for
long functions, and the full schema, see
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Exit Codes

`certfix check`:

| Code | Meaning |
|------|---------|
| 0 | No violations found |
| 1 | Violations found |
| 2 | Usage, configuration, model, or runtime error |

`certfix fix`:

| Code | Meaning |
|------|---------|
| 0 | Command completed and no failed fixes were reported. Source files were not changed. |
| 1 | At least one detected issue could not be fixed or failed validation |
| 2 | Usage, configuration, model, or runtime error |

`certfix doctor` is diagnostic. Warnings such as a disconnected local server do
not change its exit code unless config loading itself fails. Use `certfix check`
exit codes for CI violation gating.

## Limitations

- C only. C++ is not supported.
- Supported CERT-C coverage is limited to the 115 bundled rule targets.
  CERT-C recommendations are not supported. See
  [docs/SUPPORTED_RULES.md](docs/SUPPORTED_RULES.md) for the supported rule
  catalog.
- Directory input scans `.c` / `.h` files. `certfix-output/` is skipped.
- certfix does not detect every violation, and detected violations are not
  always repaired correctly.
- Analysis is file/function scoped, not whole-program semantic analysis.
- Repair assumes one violation per function. Multiple violations in one function
  are not supported as a single repair task.
- Functions up to about 200 lines are the expected case. Results may become less
  stable above that, and functions over about 300 lines should be split before
  running certfix. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for
  best-effort token/context tuning.
- Header handling is limited. System headers and deep include graphs are not
  fully expanded.
- v0.2.0 fixed-code candidates are comment-stripped; comment-preserving repair
  is not implemented.
- LLM output is not deterministic. The exact issue candidates, fixed-code
  candidates, and explanation text can vary by model, provider, prompt profile,
  runtime settings, and upstream model updates.
- Source files are not modified. Review generated fixed-code candidates and
  patches, then merge changes manually.
- Validation gates reduce risk but do not guarantee semantic preservation,
  security correctness, or compile success in your target build environment.
- For release test set success rates and caveats, see
  [docs/BENCHMARK_SUMMARY.md](docs/BENCHMARK_SUMMARY.md).
- Local LLMs require a separately running `llama-server`. certfix does not
  auto-start it or load GGUF files in-process.
- API routes send source code to the configured provider.

## Documentation

The main public documents are:

| Document | Purpose |
|----------|---------|
| [docs/INDEX.md](docs/INDEX.md) | Documentation index |
| [docs/DOCKER.md](docs/DOCKER.md) | API-only Docker and local Qwen Docker Compose usage |
| [docs/EXAMPLE_OUTPUT.md](docs/EXAMPLE_OUTPUT.md) | Before/after example and generated artifact walkthrough |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Config lookup, bundled profiles, common edits, include paths, advanced routing, and token/context tuning |
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
