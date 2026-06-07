# Research Notes

certfix is developed with a clear boundary between the release-side
implementation and the experiment-side research workflow.

The public GitHub repository is intended to present the release-side CLI,
public documentation, bundled configuration examples, tests, and packaging
surface for the current public release. Normal users should be able to
understand and use certfix from the README, release docs, configs, and CLI help
without needing any experiment-side assets.

Historical research and internal maintainer records are retained outside the
initial public repository for maintainer traceability. They include design
notes, backlog records, model intake notes, local user notes, and
experiment-derived reports that explain why earlier implementation choices were
made.

Research archive files are not user setup documentation. If a separately
sanitized archive is published later, it may mention older model names, older
plans, older benchmark values, internal experiment phrasing, or approaches that
are no longer the release default. Those references should not be interpreted as
current public requirements or as the recommended user workflow.

Local-only files under `docs/internal/` are maintainer notes and are not part of
the public release surface.

For the public release path, prefer these documents:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/QWEN36_MTP_RUNTIME.md`
- `docs/BENCHMARK_SUMMARY.md`

The public workflow is centered on the Qwen3.6 local MTP profile and the
bundled public configs. SFT artifacts, local experiment checkpoints,
experiment-side datasets, and archived research outputs are not required for
normal CLI usage.

## AI-Assisted Development

certfix was developed with AI coding assistants, including Codex and Claude
Code. They were used for implementation support, design review, code review,
documentation drafting, and release-readiness checks.

Proprietary LLM outputs were not used as training targets, training-data labels,
or per-record training-data audit decisions for the public release path.
SFT artifacts and experiment-side datasets are not required for normal CLI
usage.

Benchmark claims should be read with the caveats in
`docs/BENCHMARK_SUMMARY.md`. Historical benchmark reports are maintainer
context, not standalone public performance claims for the current default
release path.
