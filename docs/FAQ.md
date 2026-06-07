# FAQ

This FAQ answers common questions about certfix as a public CLI tool. It is meant
to complement the usage guide in [`README.md`](../README.md), the design
explanation in [`DESIGN_RATIONALE.md`](DESIGN_RATIONALE.md), the architecture
overview in [`ARCHITECTURE.md`](ARCHITECTURE.md), and the scope notes in
[`LIMITATIONS.md`](LIMITATIONS.md).

## General

### What is certfix?

certfix is an LLM-assisted CLI for C code. It detects CERT-C issue candidates
and generates reviewable fixed-code candidates and patches.

certfix is designed to support review workflows. It writes reports, candidate
fixed files, and patches to an output directory; it does not silently edit user
source files.

### Is certfix based on the assumption that LLMs cannot understand C code?

No. Strong LLMs can be highly capable at localized C-code repair. certfix is
based on a different assumption: model use is an engineering trade-off.

A hosted frontier model may be best for difficult cases, but it may be too
costly or may not be allowed to receive confidential source code. A lower-cost
API model may be good enough for some stages. A local model may be preferred for
bulk runs, repeatability, cost control, offline use, or source-code privacy even
if it is weaker on some metrics. Some cases should still be escalated to human
review.

certfix exists to make that trade-off explicit through model routes, validation
gates, reports, and reviewable artifacts.

### Is certfix a static analyzer?

No. certfix complements static analyzers, but it is not a replacement for them.

A static analyzer primarily reports potential issues. certfix focuses on the
next step: generating a candidate fix and related artifacts that a developer can
review. In practice, certfix should be used alongside compilers, tests, static
analysis, and human code review.

### Why does certfix target CERT-C?

CERT-C provides a clear rule-oriented framework for safer C programming. That
makes it a practical target for LLM-assisted detection, rule selection, repair
prompting, validation, and machine-readable reporting.

certfix targets C code and a bundled catalog of 115 CERT-C rule targets. It does
not claim full CERT-C compliance.

### What languages and rules are supported?

certfix supports C source code. C++ is not supported.

The supported public rule catalog is limited to the 115 bundled CERT-C rule
targets listed in [`SUPPORTED_RULES.md`](SUPPORTED_RULES.md). CERT-C
recommendations are not supported.

### Does certfix guarantee that all CERT-C violations will be found?

No. certfix detects issue candidates and may miss violations. It is not a
whole-program semantic analyzer, and it does not guarantee complete coverage of
the supported rule targets.

Use certfix as an assistance tool together with existing static analysis, build
checks, tests, and review.

### What does certfix output?

`certfix check` writes machine-readable reports such as JSON, SARIF, and a
summary report.

`certfix fix` adds fixed-code candidate files and patch files. Optional
comment-merge modes can also add comment-restored review artifacts.

### Does certfix modify source files directly?

No. certfix does not modify source files in place.

The intended workflow is to review the generated reports, fixed-code candidates,
patches, and validation results, then manually merge changes if appropriate.

## Runtime And Data Boundaries

### Why is Docker the recommended runtime?

Docker gives users a clearer and more reproducible execution boundary.

In the normal Docker workflow, source files are mounted read-only under `/input`
and reports, fixed-code candidates, and patches are written under `/output`.
This makes the input/output boundary explicit and helps avoid accidental source
tree mutation.

### Can certfix be used without Docker?

Yes. The underlying `certfix` CLI can be installed and run directly for manual
or advanced use.

Docker is recommended for normal use because it reduces setup friction and makes
the runtime boundary easier to understand.

### What are the local, API, and hybrid routes?

certfix supports three broad runtime routes:

- **Local-only**: all model-backed steps use a local OpenAI-compatible server,
  such as a local `llama-server`. This route keeps source code local.
- **API-only**: model-backed steps use an external API provider. This is often
  the easiest first run, but source code is sent to the configured provider.
- **Hybrid**: some steps use a local model and some steps use an API provider.
  Source code may be sent to the provider for API-routed steps.

Choose the route based on your data policy, available hardware, cost, and
quality requirements.

### Is model choice only a benchmark decision?

No. Benchmark results are useful, but model choice is also a route-policy
decision.

Hosted models may offer stronger repair or review capability, but they can add
API cost, latency, source-code exposure, provider dependence, and operational
opacity. Local models can improve source-code confidentiality, repeat execution
cost, offline use, reproducibility, and model-version control. Hybrid routes let
users decide which stages can accept API exposure and which stages should stay
local.

The practical question is which model, programmatic gate, coding agent, or human
reviewer should handle each stage under the project's quality, cost, latency,
confidentiality, reproducibility, and trust constraints.

### Does certfix send source code to external providers?

Only when an API-routed step is configured.

Local-only mode is intended for cases where source code must stay local. API-only
and hybrid routes may send source code to the configured provider. If
`--comment-merge-audit` uses an API provider, original and restored comments may
also be sent to the configured review model.

Users should confirm their project data policy before using API-backed routes.

### Why keep a local route?

A local route is important for source-code confidentiality, repeatability, and
cost control. It is also useful for environments where source code cannot be sent
to an external provider.

The trade-off is that local inference requires compatible hardware, a running
model server, and sufficient model quality for the configured workflow.

### What can users configure?

Users can configure include/exclude paths, compiler settings, model routes,
local/API/hybrid profiles, provider settings, and advanced step routing.

Most users should start from a bundled profile and edit only the necessary
fields.

## Repair And Validation

### Why not apply LLM output directly?

LLM output can be useful and high quality, but a generated repair is still a
candidate until the project decides to adopt it.

certfix treats generated fixes as candidates, not trusted source changes. This
is why it writes reviewable artifacts, runs validation gates, and keeps final
merge decisions outside certfix.

### What are validation gates?

Validation gates are checks applied to fixed-code candidates before they are
reported as validation-passed by certfix.

The current workflow can include format checks, compile checks, target violation
removal, semantic review, programmatic regression checks, retry classification,
and one validate-guided retry when enabled.

### What does `fixed` mean in certfix reports?

`fixed` means the fixed-code candidate passed the enabled certfix validation
gates for that run. It does not mean that the change is semantically equivalent,
secure in the target environment, or ready to merge without project-specific
tests and review.

### Do validation gates prove that a fix is correct?

No. Validation gates reduce risk, but they do not prove semantic preservation,
security correctness, or build success in the user's target environment.

A candidate that passes certfix validation still needs normal project review,
testing, and integration checks.

### Why is compile success not enough?

Compile success only shows that the generated code is syntactically acceptable
for the configured compiler check. It does not prove that the original behavior
was preserved, that the fix is safe in the target environment, or that no new
logic bug was introduced.

This is why certfix combines compile checks with other validation signals and
still treats the result as a reviewable candidate.

### How does certfix handle false positives and false negatives?

False positives are handled by the review workflow: certfix does not modify
source files directly, so developers can reject unnecessary candidates.

False negatives are a limitation of the tool. certfix should be used with other
quality signals such as static analyzers, tests, and human review.

### What does retry do?

When a fixed-code candidate fails validation for a retryable reason, certfix can
feed the failure reason back into a prompt and generate one additional candidate.

Retry is intentionally limited. If a model repeatedly fails the same repair,
unbounded retries can waste time and make results harder to reason about.

### Where can users reject an LLM-generated candidate?

Users can reject or escalate a candidate at several points:

- ignore an issue candidate from `certfix check`;
- decline to run `certfix fix`;
- reject a generated fixed-code candidate;
- reject a patch after reviewing the diff;
- reject a candidate that passed certfix gates but failed project-specific tests;
- avoid API-routed steps when source-code policy does not allow them; and
- escalate uncertain cases to a stronger model route or human review.

certfix is designed so that source adoption remains explicit and
user-controlled.

## Comment Handling

### Why are comments removed from the LLM-facing path?

Comments can be helpful to humans, but they can also contain stale intent,
incorrect explanations, disabled code fragments, or misleading rule hints.

LLM-backed analysis can lean too heavily on comments instead of reasoning from
executable C code. certfix therefore keeps the LLM-facing detection, repair, and
validation path comment-stripped where the release pipeline depends on
preprocessed code.

### Does removing comments lose useful information?

Sometimes, yes. Comments can contain useful human intent.

certfix treats this as a trade-off. The validation path is kept comment-stripped
to avoid stale or misleading natural-language context steering the model. When
users want comment-preserved review artifacts, they can opt into comment-merge
features after the comment-stripped candidate has already passed validation.

### What is `--comment-merge`?

`--comment-merge` generates additional review-only artifacts that conservatively
restore comments from the original source onto an already validated
comment-stripped fixed-code candidate.

It does not change the main validation path. The existing `fixes/` and
`patches/` artifacts remain the validation-first comment-stripped outputs.

### What is `--comment-merge-audit`?

`--comment-merge-audit` adds an LLM-backed audit for restored comments. It can
suppress comment-merged artifacts when restored comments appear stale,
misleading, or inconsistent with the fixed code.

This audit is a review aid, not a proof that comments are complete or correct.
If the audit uses an API provider, original and restored comments are sent to
the configured review model.

## Evaluation And Benchmarks

### How is certfix evaluated?

certfix evaluation is separated by workflow stage: detection, rule selection,
repair, validation, retry, and artifact generation.

The public benchmark summary reports aggregate release-test-set measurements.
Those measurements are intended as release-quality references under specific
conditions, not as guarantees for arbitrary user code.

### How should benchmark results be read?

Benchmark numbers should be read together with the model route, evaluation set,
validation settings, and caveats.

Different metrics answer different questions. Detection F1, Rule hit, Gold
fixed, Safe FP fixed, and Retry success are not interchangeable. A model can
perform well on one metric while creating risk on another.

### Why is the evaluation dataset not bundled with the public package?

The public package does not bundle the release evaluation dataset or derived
split metadata. The published documentation reports aggregate results, rule
coverage, difficulty mix, metrics, and caveats instead.

This helps keep the public package focused on the CLI while preserving the
licensing constraints, integrity, and boundaries of the evaluation materials.

### Does certfix performance improve as LLMs improve?

Potentially, yes. certfix is designed around configurable model routes, so better
models can improve detection, repair, validation, or review quality.

However, better model quality does not remove the need for route policy,
validation gates, reviewable artifacts, and clear runtime/data boundaries.

## Practical Use

### How should certfix be used in a real workflow?

A typical workflow is:

1. run `certfix check` on a source folder;
2. inspect the JSON/SARIF/summary reports;
3. run `certfix fix` when repair candidates are desired;
4. review generated fixed-code candidates and patches;
5. run project-specific tests, builds, static analysis, and review; and
6. manually merge changes when appropriate.

CI can use `certfix check` for issue-candidate gating, while `certfix fix` is
better treated as a candidate-generation step for developer review.

### What should users review manually?

Users should review at least:

- the detected rule and location;
- the generated fixed-code candidate;
- the patch diff;
- validation results;
- any semantic-review caveats;
- comment-merged artifacts, if enabled; and
- project-specific test/build results outside certfix.

### What are certfix's biggest limitations?

The main limitations are:

- C only;
- limited to the 115 bundled CERT-C rule targets;
- no CERT-C recommendations;
- file/function-oriented analysis rather than whole-program analysis;
- expected function size is about 200 lines, and functions over about 300 lines
  should be split before repair;
- repair assumes one violation per function;
- no guarantee of semantic preservation or security correctness;
- LLM output is non-deterministic; and
- local routes require a separately running compatible model server.

See [`LIMITATIONS.md`](LIMITATIONS.md) for the full scope and caveats.

### Why does certfix keep human review in the workflow?

Human review is kept in the current public workflow as an adoption and
governance boundary, not as a claim that AI repair cannot be automated.

A stronger coding agent could consume certfix reports, patches, validation
results, and failure reasons to revise candidates or prepare merge-ready changes.
However, full automation depends on project trust, test coverage, source-code
policy, API cost, local model quality, reproducibility, and responsibility
boundaries.

certfix therefore exposes reviewable artifacts first. As models improve and
costs fall, users can route more steps to local models, API models, coding
agents, or human reviewers according to their own risk and cost policy.

### Is certfix intended to replace human code review?

No. certfix is intended to generate structured, reviewable artifacts that can
make review more efficient.

The final decision to accept, modify, or reject a candidate fix remains with the
developer or maintainer.
