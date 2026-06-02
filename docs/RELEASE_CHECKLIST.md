# Release Checklist

Use this checklist before publishing a certfix release.

For non-runtime checks, run:

```bash
python3 -m build --sdist --wheel
python3 scripts/check_release_readiness.py
```

The readiness script covers public config loading, bundled config resources,
`certfix config --list`, public-surface internal detail scans, dependency
metadata, and wheel config packaging. Runtime and external API checks remain
manual because they depend on local servers and provider credentials.

## Configs

- [ ] README-facing configs load with `Config.load()`:
  - `configs/qwen36-mtp-local.yaml`
  - `configs/qwen36-mtp-docker.yaml`
  - `configs/qwen36-mtp-check.yaml`
  - `configs/deepseek-v4-flash-openrouter.yaml`
  - `configs/deepseek-v4-flash-api.yaml`
  - `configs/gemini-3-flash-preview-openrouter.yaml`
  - `configs/examples/local-detection-deepseek-fix.yaml`
  - `configs/examples/local-detection-deepseek-fix-docker.yaml`
  - `configs/examples/deepseek-gemini-step-overrides.yaml`
- [ ] Local-only configs remain ignored by git:
  - `configs/local-*.yaml`
  - `configs/local-*.yml`
- [ ] Public configs do not contain local absolute paths, internal experiment
  output paths, or private API keys.
- [ ] Bundled configs are present in the wheel and `certfix config --list`
  works from a wheel install.

## Packaging

- [ ] Base install has only lightweight CLI/config dependencies.
- [ ] API users can install with `pip install certfix`.
- [ ] Local server users can install with `pip install certfix`.
- [ ] Obsolete ML detection code and dependencies are not included in the
  public package.
- [ ] Wheel metadata does not expose `llama-cpp-python`.

## Runtime

- [ ] Local Qwen3.6 MTP server starts with the documented command.
- [ ] `certfix doctor --config configs/qwen36-mtp-local.yaml` reports the
  selected local profile clearly.
- [ ] `certfix config qwen36-mtp-local --output .certfix.yaml` writes the
  bundled local profile.
- [ ] `certfix config qwen36-mtp-docker --output .certfix.yaml` writes the
  bundled Docker Compose local profile.
- [ ] `certfix check <sample.c> --config configs/qwen36-mtp-local.yaml --output-dir certfix-output` runs.
- [ ] `certfix fix <sample.c> --config configs/qwen36-mtp-local.yaml --output-dir certfix-output`
  runs on a small smoke case.
- [ ] Docker wrapper help works from the built image:
  `docker run --rm certfix-ci certfix-docker --help`.
- [ ] API-only Docker wrapper can mount source at `/input:ro` and output at
  `/output`.
- [ ] Local `llama-server` Docker Compose config resolves with `SOURCE_DIR`,
  `OUTPUT_DIR`, `HOST_MODEL_DIR`, `HOST_MODEL_CACHE_DIR`, and
  `LLAMA_MODEL_PATH` set.

Latest smoke: local Qwen3.6 MTP check/fix passed on
`tests/fixtures/mem30_use_after_free.c` with `draft-mtp` enabled in the server
log. Wheel install-equivalent config list/write/doctor/check also passed.

## API Profiles

- [ ] `.env` is not committed.
- [ ] OpenRouter profiles use `OPENROUTER_API_KEY`.
- [ ] DeepSeek direct profile uses `DEEPSEEK_API_KEY`.
- [ ] API profile documentation states that source code is sent to the
  configured provider.
- [ ] DeepSeek direct API connectivity smoke is current enough for release.

## Quality Gates

- [ ] `pytest tests/integration/test_cli.py -q`
- [ ] `pytest tests/unit/test_config.py -q`
- [ ] `ruff check src/ tests/ scripts/`
- [ ] `python3 -m build --sdist --wheel`
- [ ] Local server unavailable regression: `qwen36-mtp-local` check/fix exits
  2 instead of reporting "No violations found".
- [ ] `git diff --check`
- [ ] `git status --short` is clean before tagging.

## Documentation

- [ ] README Getting Started commands use real public config profiles.
- [ ] README distinguishes local, cheap API, direct DeepSeek API, quality API,
  and advanced step-routing profiles.
- [ ] Docker docs distinguish API-only, local `llama-server` Compose, and hybrid
  Compose routes and state the host GPU/runtime requirements.
- [ ] Public docs avoid internal Phase/Run/checkpoint identifiers as primary
  user guidance.
- [ ] `CLAUDE.md` and `docs/research-archive/` are not present in the initial
  public repository.
- [ ] `THIRD_PARTY_NOTICES.md` is present and references SARIF and CERT-C rule
  metadata boundaries.
- [ ] Wheel users can read third-party notices:
  `unzip -l dist/certfix-0.3.1-py3-none-any.whl | grep THIRD_PARTY_NOTICES`
- [ ] Third-party evaluation sample files such as Juliet or PrimeVul-derived
  `*samples.jsonl.gz` files are not bundled in the initial public repository.
- [ ] `eval-splits/` is not bundled in the initial public repository or sdist.
- [ ] Any internal experiment material copied into public docs has been edited
  for public release wording.
