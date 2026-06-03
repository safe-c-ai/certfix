# certfix Architecture

## Overview

certfix is a CLI tool for detecting CERT-C issue candidates and generating
fixed-code candidates for C source code with LLMs.

This document describes the current public release implementation. The default
local workflow is centered on Qwen3.6-27B MTP served by an external
OpenAI-compatible `llama-server`. API profiles use the same OpenAI-compatible
backend interface.

## Design Goals

1. **Simple CLI surface**: `check` detects issue candidates, `fix` generates
   fixed-code candidates, and `config` writes bundled profiles.
2. **Safe by default**: source files are not edited. Reports, fixed-code
   candidates, and patches are written as separate artifacts.
3. **Local-first default**: the primary public profile uses a local
   Qwen3.6-27B MTP server. Cloud/API profiles are optional.
4. **Explicit runtime boundary**: certfix talks to local servers and cloud
   providers through OpenAI-compatible HTTP APIs. It does not load GGUF files
   in-process.
5. **Machine-readable output**: JSON/SARIF output and exit codes are available
   for automation, while validation caveats remain explicit.

certfix uses a bundled compact catalog of 115 CERT-C rule targets. See
[SUPPORTED_RULES.md](SUPPORTED_RULES.md) for category coverage and catalog
limitations.

## Commands And Artifacts

| Command | Purpose | Main artifacts |
| --- | --- | --- |
| `certfix config <profile>` | Print or write a bundled profile | `.certfix.yaml` when `--output` is used |
| `certfix doctor` | Diagnose config, API keys, compiler, and local server reachability | console diagnostics only |
| `certfix check <path>` | Detect CERT-C issue candidates | `certfix-output/reports/check.json`, `check.sarif`, `summary.json` |
| `certfix fix <path>` | Generate fixed-code candidates and validation reports | `certfix-output/fixes/`, `patches/`, `reports/fixes.json`, `fixes.sarif`, `summary.json` |
| `certfix setup` | Show optional model-file diagnostics; normal API and external `llama-server` paths do not require it | diagnostic output only |

If `--output-dir` is omitted, artifacts are written under `certfix-output/` in
the target directory. The source tree is not modified.

Directory input scans `.c` and `.h` files and skips `certfix-output/` plus any
configured `check.exclude` entries.

## Runtime Backends

certfix has one public backend interface for model calls: an OpenAI-compatible
chat-completions API.

- **Local default**: `configs/qwen36-mtp-local.yaml` points to
  `http://127.0.0.1:8952/v1`, where the user runs an MTP-capable
  `llama-server` for `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL`.
- **Local Docker Compose**: `configs/qwen36-mtp-docker.yaml` uses the same
  Qwen3.6-centered pipeline but points to
  `http://llama-server:8952/v1`, the service name used by
  `docker-compose.local-qwen36.yml`.
- **API profiles**: OpenRouter and DeepSeek API profiles use the same request
  path but send source code to the configured provider.
- **Step routing**: advanced profiles can route detection, repair, retry, and
  validation steps to different configured roles.

The public path does not expose `llama-cpp-python` or other in-process
GGUF loading.

## Main Pipelines

certfix has two main user-facing pipelines:

- **Check pipeline**: used by `certfix check` to detect CERT-C issue candidates
  and write reports.
- **Fix pipeline**: used by `certfix fix` to detect or receive a target rule,
  generate fixed-code candidates, validate them, and write artifacts.

Both pipelines use the configured model route from `.certfix.yaml`. The fix
pipeline includes the check pipeline when it needs to infer a target rule before
repair.

## Check Pipeline

The release-default `check` path is a whole-file Qwen3.6 batch flow:

```
.c/.h files
  │
  ▼
collect target files
  │
  ▼
read each file as UTF-8 source text
  │
  ▼
preprocess comments out while preserving C string/character literals
  │
  ▼
Qwen3.6 batch detection
  - binary violation/no-violation decision
  - sequential Top-2 rule candidate generation
  - 3-permutation selector voting
  │
  ▼
normalize file path and line numbers
  │
  ▼
write text/JSON/SARIF output and reports
```

Steps:

1. Collect target `.c` and `.h` files.
2. Read each target as UTF-8 source text.
3. Preprocess comments out while preserving C string/character literals and line
   structure.
4. Send the preprocessed, comment-stripped file text to the configured Qwen3.6
   batch detection route.
5. Run binary violation detection, rule candidate generation, and
   3-permutation selector voting.
6. Normalize file paths and line numbers.
7. Write text/JSON/SARIF output and reports.

This path is selected when:

- `detection.backend` is `local_llama_server` or `api`,
- `detection.prompt_profile` is `qwen36_certfix_check_v1`, and
- the backend supports Qwen3.6 batch detection.

Connection or inference failures in this path are runtime errors, not "clean"
results.

### Generic Detector Path

A generic function-chunk detector remains available for compatible non-default
profiles. It:

- blanks comments while preserving line structure,
- resolves local `#include "..."` headers as auxiliary context,
- splits files into function-level chunks with a brace-counting heuristic,
- prepends header and preceding non-function context,
- maps reported line numbers back to the original file,
- deduplicates by `(rule_id, line)`, and
- applies `certfix:ignore` filters.

This generic path is not the main release-default Qwen3.6 check route.

### Comment Handling

certfix intentionally removes C comments before LLM-facing check and fix
processing where the pipeline uses preprocessed chunks or fixed-code candidates.
This is not an accidental formatting loss. Comments can contain stale intent,
incorrect explanations, disabled code fragments, or misleading rule hints, and
LLM-backed analysis can overfit to that natural-language context instead of the
executable C code.

This policy comes from the experiment-side SFT and evaluation history. Earlier
comment-present data made models appear stronger than they were: the model could
learn the explanatory comment pattern or rule hint instead of the semantic
properties of the C code. In those runs, result quality did not track code
difficulty reliably, which made model comparisons and release decisions
misleading. Comment removal became the release invariant to reduce shortcut
learning and evaluation leakage.

The release pipeline therefore keeps the analysis and validation path
comment-stripped:

- detection should reason over code structure and rule context, not comments;
- repair should generate a code candidate that can be compiled and validated
  without depending on comments;
- validation and programmatic checks compare executable structure, not comment
  text.

When `certfix fix --comment-merge` is enabled, comment-preserving output is a
final artifact-generation step that merges comments back onto an already
validated comment-stripped candidate. It does not reintroduce comments into the
LLM-facing check, repair, or validation inputs. With `--comment-merge-audit`,
an additional LLM audit checks whether restored comments look stale or
misleading before comment-merged artifacts are written. That audit is the only
opt-in comment-restoration path that sends original/restored comments to a
configured review model.

## Fix Pipeline

`certfix fix` is artifact-only. It does not patch source files in place.

The release-default `fix` path is:

```
.c/.h files
  │
  ▼
collect target files
  │
  ▼
read each file as UTF-8 source text
  │
  ▼
strip comments for the LLM-facing repair input
  │
  ▼
select target rule
  - use --rule when provided
  - otherwise run configured detection
  │
  ▼
generate complete fixed-code candidate
  │
  ▼
strip C comments from the candidate
  │
  ▼
run validation gates
  - format
  - compile
  - target violation removal
  - semantic review
  - programmatic regression checks
  │
  ▼
run one validate-guided retry when enabled and retryable
  │
  ▼
optional final comment-merged output artifact when --comment-merge is enabled
  - optional restored-comment audit when --comment-merge-audit is enabled
  │
  ▼
write reports, patches, and fixed-code candidates
```

Steps:

1. If `--rule` is provided, use the requested rule set.
2. Otherwise, when the configured repair profile requires a rule, run detection
   and select a target rule for the repair attempt.
3. Strip comments from the full source file for the LLM-facing repair input while
   keeping the raw original source for artifact diffs and optional comment merge.
4. Send the complete comment-stripped source file plus rule context to the
   configured repair backend.
5. Extract a complete fixed-code candidate from the model output.
6. Strip C comments from the fixed-code candidate.
7. Run enabled validation gates.
8. If validation fails with a retryable category, run one validate-guided retry.
9. When `--comment-merge` is enabled, optionally generate a comment-merged
   output artifact after validation has already accepted the comment-stripped
   candidate. When `--comment-merge-audit` is enabled, suppress that artifact if
   the restored-comment audit rejects it.
10. Write reports, patches, and fixed-code candidates under the output directory.

The public Qwen3.6 profile uses:

- `simple_repair_profile: qwen36_27b_complete_repair_rule_guided_v1`
- `validate_guided_retry: true`
- `retry_max_attempts: 1`

## Validation Gates

Generated fixed-code candidates are accepted as successful only when all enabled
gates pass.

| Gate | Purpose |
| --- | --- |
| Format check | Reject empty, placeholder, or malformed fixed-code output |
| Compile check | Run the configured C compiler, usually `gcc -fsyntax-only` |
| Target violation removal | Check that the selected target rule no longer remains |
| Semantic review | Ask the configured reviewer role whether material behavior appears preserved |
| Programmatic regression checks | Block known structural regression patterns |
| Retry classification | Decide whether a failed candidate is retryable |

These gates reduce risk but do not guarantee semantic preservation, security
correctness, or build success in the user's target environment.

## Configuration Lookup

The normal public workflow starts by writing a bundled profile:

```bash
certfix config qwen36-mtp-local --output .certfix.yaml
```

Config lookup is:

1. `--config <file>` when supplied
2. `.certfix.yaml` in the current working directory
3. built-in defaults

Built-in defaults are intentionally incomplete for normal public use. Users
should create `.certfix.yaml` from a bundled profile before running model-backed
commands.

API keys are read from the shell environment or a local `.env` file. Existing
environment variables take precedence over `.env`.

## Scope Boundaries

- C is the supported language. C++ is out of scope.
- The release-default check path analyzes files independently and does not build
  a whole-program call graph.
- The generic detector can use limited local header context, but certfix does
  not fully expand system headers or deep include graphs.
- Repair is designed for one selected target rule per repair attempt. Multiple
  independent violations in the same function are not handled as one combined
  repair task.
- Fixed-code candidates under `fixes/` are comment-stripped. Optional
  `--comment-merge` artifacts are generated only after validation and are
  review aids, not the validated candidate itself. `--comment-merge-audit`
  audits restored comments before writing those review artifacts.
- Source files are never modified by certfix commands.

## Exit Codes

`certfix check`:

| Code | Meaning |
| --- | --- |
| 0 | Command completed and no violations were reported |
| 1 | Violations were reported |
| 2 | Usage, configuration, model, or runtime error |

`certfix fix`:

| Code | Meaning |
| --- | --- |
| 0 | Command completed and no failed fixes were reported |
| 1 | At least one detected issue could not be fixed or failed validation |
| 2 | Usage, configuration, model, or runtime error |

`certfix doctor` is diagnostic and may report warnings while still exiting 0.
