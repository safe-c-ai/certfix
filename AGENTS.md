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

## Release Traceability

- Public release tags such as `v0.1.0` belong to the public repository
  `safe-c-ai/certfix`.
- The development repository must use a separate source tag for each public
  release, named `public/vX.Y.Z-source`.
- Record the public tag/SHA and development source tag/SHA mapping in
  `docs/research-archive/RELEASE_TRACEABILITY.md`.
- Do not keep ambiguous `vX.Y.Z` release tags in `certfix-dev`.
- Before deciding whether current work belongs to an already-published release
  or the next release, verify the live release state instead of relying on
  memory or conversation context.
- Last live release check before the current next-release work on 2026-06-02:
  - `safe-c-ai/certfix` latest GitHub Release: `v0.2.0`.
  - `safe-c-ai/certfix-dev` latest public source tag: `public/v0.2.0-source`.
  Treat later local changes as next-release work unless the user explicitly
  says they are patching an already-published release.
- Use these checks before editing release notes, version docs, tags, or release
  instructions:

```bash
python3 - <<'PY'
import json
import urllib.request

repo = "safe-c-ai/certfix"
url = f"https://api.github.com/repos/{repo}/releases/latest"
with urllib.request.urlopen(url, timeout=15) as response:
    release = json.load(response)
print(f"{repo} latest GitHub Release: {release['tag_name']}")
PY

git ls-remote --tags dev 'refs/tags/public/v*' 'refs/tags/v*' | sort -V
```

- `safe-c-ai/certfix-dev` may not expose GitHub Releases through the public API.
  In that case, use the `public/vX.Y.Z-source` remote tags as the dev-side
  release traceability state.
- Do not rewrite release notes for an already-published public version to
  describe new unreleased work. Add a new top-level section for the next release
  instead.
- Release order is review-gated. For substantial README, docs, Docker,
  packaging, release-note, or public-boundary changes, do not treat the work as
  ready to publish until the user has reviewed the changed files or a sanitized
  review archive and explicitly approved proceeding.
- The normal order for substantial public-facing changes is:
  1. Implement changes in `certfix-dev`.
  2. Run local consistency checks that do not publish anything.
  3. Create a sanitized review archive, excluding local scratchpads, private
     research archives, evaluation splits, generated sample datasets, secrets,
     and local-only files.
  4. Wait for user review and approval.
  5. Only after approval, prepare release notes, public sync, tags, GitHub
     Release, PyPI, or GHCR publishing steps.
- If the user asks "what next?" after implementation but before review, the next
  step is review preparation and review, not publication or release finalization.

## Git And GitHub Guidance

- When giving the user Git or GitHub operation commands, explain what each
  command does, which repository/branch/tag it affects, and whether it is
  destructive or hard to undo.
- For push, tag, release, visibility, deletion, force, reset, rebase, merge,
  checkout/restore, clean, or branch deletion operations, include the expected
  pre-check and post-check commands.
- Prefer explicit repository paths in instructions when both `certfix-dev` and
  `certfix-public` are involved.

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
