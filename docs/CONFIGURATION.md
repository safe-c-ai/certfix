# Configuration Reference

certfix reads `.certfix.yaml` to choose the model route, API provider,
validation gates, and project-specific exclusions.

Most users should start from a bundled profile and edit only project-specific
settings such as excluded paths, compiler command, and include paths. Avoid
hand-editing model routes unless you are intentionally changing providers or
using advanced routing.

## File Lookup

- If `--config <file>` is passed, certfix reads that file.
- Otherwise, certfix reads `.certfix.yaml` in the current working directory.

Create a config from one of the bundled profiles:

```bash
certfix config qwen36-mtp-local --output .certfix.yaml
certfix config qwen36-mtp-docker --output .certfix.yaml
certfix config deepseek-v4-flash-openrouter --output .certfix.yaml
```

Use `--force` only when you want to overwrite an existing file.

Profile names are CLI names, not file paths. For example,
`qwen36-mtp-local` writes the bundled `configs/qwen36-mtp-local.yaml` content.

## Bundled Profiles

| Profile | Purpose |
|---------|---------|
| `qwen36-mtp-local` | Local Qwen3.6-27B MTP check and fix |
| `qwen36-mtp-docker` | Local Qwen3.6-27B MTP check and fix through Docker Compose |
| `qwen36-mtp-check` | Local Qwen3.6-27B check only |
| `deepseek-v4-flash-openrouter` | DeepSeek V4 Flash through OpenRouter |
| `deepseek-v4-flash-api` | DeepSeek V4 Flash through DeepSeek's official API |
| `gemini-3-flash-preview-openrouter` | Gemini 3 Flash Preview through OpenRouter |
| `local-detection-deepseek-fix` | Local Qwen3.6 detection with DeepSeek repair/validation |
| `local-detection-deepseek-fix-docker` | Docker Compose local Qwen3.6 detection with DeepSeek repair/validation |
| `deepseek-gemini-step-overrides` | Advanced example for per-step model routing |

List the same profiles from the CLI:

```bash
certfix config --list
```

## What To Edit

| Goal | Edit |
|------|------|
| Skip generated, vendor, or test code | `check.exclude` |
| Add header context for analysis | `detection.include_dirs` |
| Use Clang instead of GCC | `validation.compile.command` |
| Add project header directories | `validation.compile.include_paths` |
| Change local server URL or model name | `detection.api` and matching `models.<role>.api` |
| Change API provider | Start from another bundled profile |
| Route only selected steps to another model | `models` plus `pipeline.overrides` |

## Common Edits

### Exclude Paths

Use `check.exclude` to skip generated code, vendor code, tests, or output
directories.

```yaml
check:
  exclude:
    - "tests/"
    - "vendor/"
    - "build/"
```

### Compile Validation

certfix uses a C compiler during validation. The default command is `gcc`.

```yaml
validation:
  compile:
    enabled: true
    command: gcc
    args: ["-fsyntax-only"]
    include_paths:
      - "include/"
    timeout: 30
```

Use `command: clang` if your project should be checked with Clang.
Add project header directories to `include_paths`; certfix passes them to the
compiler as `-I <path>`.

### Header Context For Analysis

For analysis prompts, certfix can use non-function context from local
`#include "..."` headers. Headers are resolved from the source file directory
and from `detection.include_dirs`.

```yaml
detection:
  include_dirs:
    - "include/"
```

This context helps with types, macros, and declarations. It is separate from
`validation.compile.include_paths`, which is used by the compiler during
validation.

### API Keys

API profiles read keys from environment variables. You can export them in the
shell or place them in a local `.env` file. Existing shell environment variables
take precedence over `.env`.

`.env` example:

```dotenv
OPENROUTER_API_KEY=<openrouter-key>
DEEPSEEK_API_KEY=<deepseek-key>
```

API routes send source code to the configured provider. Confirm your project
data policy before using a cloud provider.

### Local llama-server

Local profiles use an OpenAI-compatible local `llama-server`.

```yaml
detection:
  backend: local_llama_server
  api:
    base_url: http://127.0.0.1:8952/v1
    model: unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL
    api_key_env: ""
```

The same server route is also configured under `models.<role>.api` for repair
and validation roles. If you change the local `base_url` or `model`, update both
places in profiles that include a `models` section.

Use `qwen36-mtp-local` when certfix runs on the host and talks to
`http://127.0.0.1:8952/v1`. Use `qwen36-mtp-docker` when certfix runs inside
`docker-compose.local-qwen36.yml`; that profile points to the Compose service
URL `http://llama-server:8952/v1`.

For hybrid local/API routing, use `local-detection-deepseek-fix` on the host
with a host-local `llama-server`, and use `local-detection-deepseek-fix-docker`
inside Docker Compose. The Docker profile points detection to
`http://llama-server:8952/v1` and still sends repair/validation steps to the
configured API provider.

### Long Functions And Token Limits

certfix is designed around function-level analysis. As a practical guideline,
functions under about 200 lines are the expected case. Longer functions can be
less stable because both the input context and the repaired code must fit within
the model/server limits.

There is no fixed line-count cutoff in certfix. If you need to try longer
functions, these settings may help:

- Increase the local `llama-server` context length, for example `-c 16384`
  instead of `-c 8192`.
- Increase repair output limits such as `fix.simple_max_tokens` and
  `fix.retry_max_tokens`.
- Keep the role-level `models.<role>.max_tokens` and
  `models.<role>.api.max_tokens` consistent with the repair limits.

Example:

```yaml
models:
  qwen36_local:
    max_tokens: 8192
    api:
      max_tokens: 8192

fix:
  simple_max_tokens: 8192
  retry_max_tokens: 8192
```

This is a best-effort tuning path, not a supported guarantee. Larger context and
output limits increase latency and memory use, and they do not guarantee correct
detection, repair, semantic preservation, or compile success. For large
functions, splitting the function before running certfix is still the preferred
approach.

## Advanced Routing

`models` defines named model roles. `pipeline.overrides` can route selected
steps to those roles. This is useful when you want to keep one model for
detection but use another model for repair or validation.

```yaml
models:
  gemini_3_flash_preview:
    backend: api
    profile: gemini_3_flash_preview
    api:
      base_url: https://openrouter.ai/api/v1
      model: google/gemini-3-flash-preview
      api_key_env: OPENROUTER_API_KEY

pipeline:
  overrides:
    rule_selector_voting: gemini_3_flash_preview
    fix_generation: gemini_3_flash_preview
    semantic_check: gemini_3_flash_preview
```

This is an advanced feature. Start from a bundled profile and change only the
roles you intentionally want to reroute.

## No Config File

If `.certfix.yaml` is missing and `--config` is not passed, certfix falls back to
internal defaults. Those defaults are not a usable public profile because model
routes are incomplete:

```yaml
detection:
  backend: local_llama_server
  api:
    base_url: ""
    model: ""

models: {}

fix:
  simple_repairer_role: null
```

For normal use, create `.certfix.yaml` with `certfix config <profile> --output
.certfix.yaml` before running `check` or `fix`.
