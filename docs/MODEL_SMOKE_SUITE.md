# Model Smoke Suite

This document describes the manual, model-backed smoke suite for the current
release pipeline.

The suite is intentionally not part of pytest. It loads real models and can take
many minutes on a GPU machine.

## Command

```bash
python3 scripts/run_model_smoke_suite.py \
  --config configs/qwen36-mtp-local.yaml \
  --output-dir model-smoke-results \
  --timeout 1200 \
  --strict
```

Fix smoke commands use the default `certfix fix` command, which is the current
Qwen3.6 release path.

Useful narrower runs:

```bash
python3 scripts/run_model_smoke_suite.py \
  --config configs/qwen36-mtp-local.yaml \
  --case mem30_use_after_free \
  --mode both \
  --save-fixed-code \
  --strict

python3 scripts/run_model_smoke_suite.py \
  --config configs/qwen36-mtp-local.yaml \
  --mode check
```

Simple-mode spot check:

```bash
python3 -m certfix fix \
  --config configs/qwen36-mtp-local.yaml \
  --format json \
  --output-dir model-smoke-results/manual-fix \
  tests/fixtures/mem30_use_after_free.c
```

With `configs/qwen36-mtp-local.yaml`, this uses a local Qwen3.6 MTP
`llama-server` for detection, simple repair, semantic review, and validation.
The profile uses `qwen36_27b_complete_repair_rule_guided_v1` for simple repair
and one validate-guided retry attempt. The primary repair emits a complete
source file; retry is only attempted after a retryable validation failure.

Before running MTP smoke, start a local MTP-enabled llama.cpp server for
`unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL` with `--spec-type draft-mtp
--spec-draft-n-max 2 --reasoning-budget 1024 --cache-ram 0`. See
`docs/QWEN36_MTP_RUNTIME.md`.

API profiles remain available for environments without an MTP-capable local
server. They send source code to the configured provider.

## Cases

All samples are small self-authored C snippets for smoke testing. They are not
derived from external benchmark suites. The canonical sample sources live in
`model-smoke-cases/`; the runner copies those files into temporary paths before
invoking `certfix`.

| Case | Expected rule | Fix expected by strict mode | Purpose |
|------|---------------|-----------------------------|---------|
| `mem30_use_after_free` | `MEM30-C` | yes | Primary check/fix/validation smoke |
| `exp34_null_deref` | `EXP34-C` | no | Detection and selection smoke |
| `exp33_uninitialized_read` | `EXP33-C` | no | Detection and selection smoke |
| `mem35_short_alloc` | `MEM35-C` | no | Detection and selection smoke |
| `multi_function_mem30` | `MEM30-C` | no | Multiple functions in one source file |
| `multi_file_mem30` | `MEM30-C` | no | Directory target with multiple C/header files |
| `clean_print` | none | no | Negative control |

The multi-file case verifies directory traversal and per-file detection. It is not a
cross-translation-unit semantic reasoning test.

Only `mem30_use_after_free` is currently strict on final `fixed` status. The
other positive cases are useful for observing model behavior without making the
release gate overly brittle before broader evaluation.

## Outputs

The script writes:

- copied C sample files,
- `results.jsonl` with raw command output and parsed summaries,
- `summary.json` with aggregate counts and strict failures.
- `*.fixed.c` files copied from certfix fix artifacts when `--save-fixed-code`
  is used with `--mode fix` or `--mode both`.

`model-smoke-results/` is gitignored so real-model smoke outputs can be kept in
a local checkout without being committed.

`--strict` exits nonzero when:

- a positive case does not include the expected rule in `certfix check`,
- a clean case reports violations,
- a case marked `expect_fixed` does not finish with final status `fixed`.

`--save-fixed-code` copies generated fixed-code artifacts from the per-case
`certfix-output` directory. It never edits the canonical sources in
`model-smoke-cases/` or the copied original samples in `model-smoke-results/`;
successful fixed files are written separately as `<case_id>.fixed.c`.

## Notes

Run this suite from the release workspace after `certfix setup` and
`certfix doctor` pass for the selected role config. For expensive full-pipeline
runs, start with `--case mem30_use_after_free` before running all cases.
