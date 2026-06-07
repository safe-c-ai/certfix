# Benchmark Summary: v0.1.0 Release-Test Reference

This page reports the v0.1.0 release-test reference results. It is retained as a
historical and methodological benchmark reference. It should not be read as the
current v0.4.x performance claim unless the same profile, runtime, and
validation settings are explicitly re-run for that release.

The results are safe to publish without bundling the evaluation datasets. The
current README is Docker-first for user onboarding, and runtime defaults or
recommended first-run paths may differ from this benchmark posture.

## v0.1.0 Default

The v0.1.0 default workflow is local Qwen3.6-27B MTP:

- config: `configs/qwen36-mtp-local.yaml`
- detection prompt profile: `qwen36_certfix_check_v1`
- Rule ID strategy: sequential Top-2 candidate generation with 3-permutation
  selector voting
- repair profile: `qwen36_27b_complete_repair_rule_guided_v1`
- validation: compile, violation-removal, semantic-review, programmatic checks,
  and one validate-guided retry

Use:

```bash
certfix config qwen36-mtp-local --output .certfix.yaml
certfix check examples/input/ --output-dir examples/certfix-output
certfix fix examples/input/ --output-dir examples/certfix-output
```

## Release Test Set

The main public benchmark uses a release test set maintained outside the public
package. It is used to compare release profiles before publication.

This page reports the most demanding release test set among the maintained
release evaluation suites. The results should be read as a conservative
release-quality reference, not as an average-case expectation for all user code.

- total cases: 365
- rule targets: 115 CERT-C rule targets; see
  [SUPPORTED_RULES.md](SUPPORTED_RULES.md)
- difficulty mix: 115 simple, 115 medium, 135 complex
- gold violation cases: 183
- safe control cases: 182
- target language: C
- task: run `certfix check` and `certfix fix`, then count fixed-code candidates
  accepted by the enabled validation gates

The test set is built from C cases selected for release evaluation. It contains
both known CERT-C violation cases and safe control cases, so the benchmark can
measure detection, rule selection, repair success, and false-positive behavior.
It is not used as a normal user-facing input corpus, and it is not bundled with
the package.

The structure is organized around 115 rule targets and three difficulty levels:
simple, medium, and complex. Each rule target contributes one simple, one
medium, and at least one complex case. Twenty rule targets include an additional
complex case where an extra variant is useful for release evaluation. This gives
365 total cases rather than a strict 115 x 3 = 345 grid.

Difficulty levels are defined by the shape of the code and the repair context:

- **simple**: small, direct cases where the target issue is localized and the
  intended repair is usually contained in one short function.
- **medium**: cases with more surrounding control flow, helper calls, or local
  state that require more context to identify and repair the issue.
- **complex**: cases with longer or less direct data/control flow, multiple
  related operations, or edge-case patterns that make detection and repair less
  straightforward.

Prompt and profile iteration used separate development sets. The release test
set reported here was kept separate from prompt/profile tuning and is used as a
held-out reference evaluation for v0.1.0.

The public package does not bundle test-set source files, case metadata, or
derived split metadata. The table below publishes aggregate results only.

## How To Read These Results

These benchmark numbers are measurements on the release test set, not
guarantees for user code. Read them together with the route/profile, model,
validation gates, retry policy, and test-set composition. Detection F1, Rule
hit, Gold fixed, Safe FP fixed, and Retry success measure different parts of
the workflow, so no single number fully represents certfix quality.

These results are intended to illustrate route selection rather than a single
winner. The practical question is not only which model fixes the most gold cases,
but which route gives an acceptable balance of repair quality, safe-control
behavior, cost, latency, source-code exposure, reproducibility, and provider
stability.

API-backed results should be read as measurements for the listed provider route
at the time of evaluation. Hosted model APIs may change due to upstream model
updates, routing changes, provider-side degradation, rate limits, policy
changes, or pricing changes. For this reason, certfix treats benchmark results
as route references rather than permanent model guarantees.

Metric notes:

- **Detection F1**: binary violation/no-violation detection F1 over all 365
  cases.
- **Rule hit**: gold-rule hit rate over the 183 gold violation cases.
- **Gold fixed**: gold violation cases that reached final `fixed` status.
- **Safe FP fixed**: safe control cases that were falsely detected and then
  accepted as fixed-code candidates. Lower is better. Safe FP fixed is a risk
  metric: unnecessary repair candidates create review burden and can introduce
  avoidable change risk.
- **Retry success**: conditional validate-guided retry success among cases where
  the primary repair failed a retryable validation category. This is not a
  whole-test-set repair rate.
- **Est. API cost**: estimated external API cost for the full 365-case run,
  computed from measured prompt/completion token usage and listed OpenRouter
  prices on 2026-05-31. It excludes local GPU cost, provider-side price changes,
  taxes, caching effects, and account-specific discounts.
- **Mean elapsed**: mean wall-clock seconds per case in the measured run. Local
  hardware, provider latency, and retry frequency affect this value.

| Profile | Route | Detection F1 | Rule hit | Gold fixed | Safe FP fixed | Est. API cost | Mean elapsed |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.6-27B local | local Qwen3.6 release path | 88.0% | 133/183 = 72.7% | 127/183 = 69.4% | 15 | $0.00 | 7.38s |
| DeepSeek V4 Flash | OpenRouter API only | 74.5% | 127/183 = 69.4% | 134/183 = 73.2% | 56 | ~$0.58 | 23.08s |
| Gemini 3 Flash Preview | OpenRouter API only | 80.3% | 141/183 = 77.0% | 152/183 = 83.1% | 49 | ~$2.73 | 8.07s |
| Local detection + DeepSeek fix | Qwen3.6 local detection, DeepSeek repair/validation | 78.7% | 123/183 = 67.2% | 133/183 = 72.7% | 34 | ~$0.07 | 19.97s |

Validate-guided retry outcomes for the same runs:

| Profile | Retry success | Gold retry success | Safe FP retry accepted |
| --- | ---: | ---: | ---: |
| Qwen3.6-27B local | 23/68 = 33.8% | 22/57 = 38.6% | 1/11 = 9.1% |
| DeepSeek V4 Flash | 17/82 = 20.7% | 11/39 = 28.2% | 6/43 = 14.0% |
| Gemini 3 Flash Preview | 8/27 = 29.6% | 5/13 = 38.5% | 3/14 = 21.4% |
| Local detection + DeepSeek fix | 13/49 = 26.5% | 9/26 = 34.6% | 4/23 = 17.4% |

A retry success means the retry output passed the enabled validation gates
and was accepted as the final fixed-code output. For safe-control cases, an
accepted retry is still counted as a safe false positive, so lower is better.
Validation gates reduce risk, but do not guarantee semantic preservation,
security correctness, or compile success in a user's target build environment.

Interpretation:

- Local Qwen3.6 is the default because it keeps source code local and has the
  best safe-control behavior among the listed routes.
- Gemini 3 Flash Preview produced the highest fixed-gold count in this test set,
  but it sends source code to the configured API provider and had more accepted
  safe false positives than local Qwen3.6.
- DeepSeek V4 Flash is the lower-cost API direction, but this test set shows weaker
  binary detection and more safe false positives than the local default.
- The combined local-detection + DeepSeek route reduces API exposure compared
  with API-only routes, but it did not outperform the local default on this
  release test set.

## Juliet Reproducible Reference

Juliet is useful as a public reference benchmark because the upstream suite is
publicly available, versioned, and distributed as public-domain benchmark
material by its official records. certfix does not bundle Juliet sources or
derived Juliet split metadata; users who want to reproduce Juliet runs should
obtain the suite from the official sources:

- NIST SARD test suite 112, Juliet C/C++ 1.3:
  `https://samate.nist.gov/SARD/test-suites/112`
- Zenodo record for Juliet Test Suite for C/C++ 1.3:
  `https://zenodo.org/records/4701387`

The reference run below used a local, maintainer-generated cap-10 Juliet subset
selected from official Juliet C/C++ 1.3 cases that map to certfix-supported
CERT-C targets. The subset used C/header-compatible cases where the release
compile validation could run meaningfully. It included both known violation
cases and corresponding safe controls:

- total cases: 578
- mapped CERT-C targets: 31
- gold violation cases: 299
- safe control cases: 279
- profile: Qwen3.6-27B local release path
- config: `configs/qwen36-mtp-local.yaml`
- task: run `certfix check` and `certfix fix`, then count fixed-code candidates
  accepted by the enabled validation gates

| Profile | Detection F1 | Rule hit | Gold fixed | Safe FP fixed | Compile env missing | Retry success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.6-27B local | 92.0% | 220/299 = 73.6% | 183/299 = 61.2% | 10 | 28 | 29/75 = 38.7% |

This Juliet result should be treated as a reference measurement, not a guarantee
or a primary release-quality claim. Local LLM output is not guaranteed to be
deterministic, so exact results can vary across model builds, runtime settings,
hardware, and reruns. Juliet is also synthetic and organized around CWE-style
test cases, while certfix reports CERT-C rule targets; the mapping, filtering,
and cap policy affect the final numbers.

## Local MTP Runtime Smoke

The release-default local profile also passed a model-backed smoke run on the
self-authored `MEM30-C` fixture with an MTP-capable `llama-server`:

- `certfix doctor --config configs/qwen36-mtp-local.yaml`
- `certfix check tests/fixtures/mem30_use_after_free.c --config configs/qwen36-mtp-local.yaml`
- `certfix fix tests/fixtures/mem30_use_after_free.c --config configs/qwen36-mtp-local.yaml --output-dir certfix-output`

The smoke confirms that the documented config, local server route, detection,
repair, compile validation, violation-removal validation, and semantic-review
gate are connected. It is a runtime smoke, not a broad quality benchmark.

## Caveats

- These numbers are release test set measurements, not guarantees for user code.
- Validation gates reduce risk but do not guarantee semantic preservation,
  security correctness, or compile success in a user's target build environment.
- API costs and latency depend on provider pricing, routing, retries, and
  prompt/token accounting at the time of use.
- Earlier multi-model experiment reports are maintainer context and should not
  be read as v0.1.0 default claims.
- The public package does not bundle third-party evaluation samples or derived
  evaluation split metadata, such as Juliet or PrimeVul-derived
  `*samples.jsonl.gz` files and `eval-splits/` metadata.
- Juliet reference numbers depend on the CWE-to-CERT mapping, subset cap,
  language/header filtering, compiler setup, and local model runtime. They
  should not be read as average-case expectations for user code.
