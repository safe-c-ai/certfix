# Limitations

certfix is an LLM-assisted tool. It generates reports, fixed-code candidates,
and patches for human review; it does not guarantee complete CERT-C coverage,
semantic preservation, or security correctness.

## Language And Rule Coverage

- C only. C++ is not supported.
- Supported CERT-C coverage is limited to the 115 bundled rule targets.
- CERT-C recommendations are not supported.
- See [SUPPORTED_RULES.md](SUPPORTED_RULES.md) for the supported rule catalog.

## Analysis Scope

- Directory input scans `.c` / `.h` files.
- `certfix-output/` is skipped.
- Analysis is file/function scoped, not whole-program semantic analysis.
- Header handling is limited. System headers and deep include graphs are not
  fully expanded.
- certfix does not detect every violation.

## Repair Scope

- Generated fixes are not always correct.
- Repair assumes one violation per function. Multiple violations in one
  function are not supported as a single repair task.
- Functions up to about 200 lines are the expected case. Results may become
  less stable above that, and functions over about 300 lines should be split
  before running certfix.
- Fixed-code candidates under `fixes/` are intentionally comment-stripped.
  Comments are excluded from the LLM-facing repair path to reduce the risk of
  stale or misleading natural-language context steering the code fix.
- `certfix fix --comment-merge` can generate additional comment-merged review
  artifacts after validation. This merge is conservative and may skip comments
  when placement is ambiguous or appears to contain disabled code.
- `--comment-merge-audit` adds an LLM audit for restored comments, but it is
  still a review aid and not a proof that comments are complete or correct.
- `--comment-merge-audit` sends original/restored comments to the configured
  review model. Do not enable it with an API provider when comments contain
  information that must stay local.

## Validation And Runtime

- Validation gates reduce risk but do not guarantee semantic preservation,
  security correctness, or compile success in your target build environment.
- LLM output is not deterministic. Exact reports, fixed-code candidates,
  patches, and explanation text can vary by model, provider, prompt profile,
  runtime settings, and upstream model updates.
- Source files are not modified by certfix. Review generated fixed-code files
  and patches, then merge changes manually if appropriate.
- Local LLMs require a separately running `llama-server`. certfix does not
  auto-start it or load GGUF files in-process.
- API routes send source code to the configured provider.

For release test set success rates and caveats, see
[BENCHMARK_SUMMARY.md](BENCHMARK_SUMMARY.md).
