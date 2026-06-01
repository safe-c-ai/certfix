# certfix Public Release Notes For Agents

This repository is the release-side workspace for `certfix`, a CLI for detecting
and repairing CERT-C issues in C source code.

## Public Boundary

- Treat this repository as publishable. Do not add local absolute paths,
  private keys, model checkpoints, evaluation datasets, cloud run details, or
  internal experiment logs.
- The initial public repository intentionally excludes `docs/research-archive/`
  and local scratchpad files such as `CLAUDE.md`.
- Research provenance belongs in internal project records or a separately
  sanitized archive, not in the primary public docs.
- SFT artifacts and experiment-side datasets are not required for normal
  v0.1.0 usage.

## Release Path

- The public v0.1.0 path is Qwen3.6-centered.
- The main local config is `configs/qwen36-mtp-local.yaml`.
- `certfix fix` uses the public Qwen3.6-centered repair path.
- API profiles are optional and send source code to the configured provider.

## Documentation Wording

- Prefer cautious claims: validation gates reduce risk; they do not guarantee
  behavior equivalence or security correctness.
- Benchmark claims should point to `docs/BENCHMARK_SUMMARY.md` and keep its
  caveats intact.
- Do not present historical model names, old benchmark values, or archived
  decisions as current release defaults.

## Development Commands

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/ scripts/
ruff format src/ tests/ scripts/
python3 -m build --sdist --wheel
python3 scripts/check_release_readiness.py
```
