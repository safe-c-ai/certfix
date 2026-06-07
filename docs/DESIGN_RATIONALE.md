# Design Rationale

This document explains the main design decisions behind certfix.
It complements the user guide in [README.md](../README.md), the implementation
overview in [ARCHITECTURE.md](ARCHITECTURE.md), and the scope notes in
[LIMITATIONS.md](LIMITATIONS.md).

certfix is an LLM-assisted CLI for detecting CERT-C issue candidates in C code
and generating reviewable fixed-code candidates and patches.

The central design choice is that certfix treats model output as repair
candidates, not trusted source changes. Strong LLMs can be highly capable at
localized C-code repair, but practical deployment is not only a capability
question. It is also a routing, validation, and governance question: which local
model, API model, stronger coding agent, programmatic gate, or human reviewer
should handle each stage under the project's quality, cost, latency,
confidentiality, reproducibility, and trust constraints?

certfix is therefore designed as a validation-first and route-aware repair
workflow rather than a direct automatic patching tool.

## 1. Problem Statement

LLMs can generate useful code repairs, and strong models can be highly capable
on localized C-code repair tasks. The deployment problem is broader than raw
model capability: repair workflows need explicit routing, validation, cost and
latency control, source-code confidentiality boundaries, reproducible artifacts,
and project-specific adoption policy.

This is especially important for C and CERT-C because:

- many defects are low-level and behavior-sensitive;
- compile success does not prove semantic correctness;
- a locally plausible fix can still be unsafe in the target build environment;
- LLM output can vary by model, provider, prompt profile, runtime setting, and
  upstream model update;
- hosted model routes can be affected by provider policy, pricing, routing,
  rate limits, and temporary service behavior;
- some environments cannot send source code to external API providers;
- some cases should be escalated to a stronger model route, coding agent, or
  human reviewer rather than retried in the same route; and
- users need auditable artifacts rather than silent in-place edits.

## 2. Core Principle: Candidates, Not Trusted Source Changes

The most important design rule is:

> Model-generated repairs are fixed-code candidates, not trusted source changes.

certfix does not modify source files in place. It writes reports, fixed-code
candidates, and patches under the output directory so users can inspect the
change, review the validation result, and decide whether to merge the candidate
into their project.

This is intentionally conservative. The goal is not to replace a static analyzer,
compiler, test suite, or human review. The goal is to shorten the path from
"diagnostic" to "reviewable repair candidate" while keeping the decision to
accept the change outside certfix.

The workflow contains explicit rejection and escalation points. Users can ignore
an issue candidate, decline to run repair, reject a generated fixed-code
candidate, reject a patch after diff review, reject a validation-passed candidate
after project tests, avoid API-routed steps when source-code policy disallows
them, or escalate uncertain cases to a stronger model route or human review.
Source adoption remains explicit and user-controlled.

## 3. Why CERT-C

CERT-C is a practical target for this workflow because it provides a clear rule
catalog for C secure-coding issues and is relevant to embedded and systems C
code. certfix uses a bundled catalog of 115 CERT-C rule targets; see
[SUPPORTED_RULES.md](SUPPORTED_RULES.md) for the supported rule list.

This scope is deliberate:

- C is the supported language.
- CERT-C recommendations are not supported.
- The rule catalog is finite and explicit.
- The workflow can combine rule context, repair prompts, validation reports, and
  human review around a known target rule.

The intent is not to claim full CERT-C compliance. certfix works on issue
candidates and repair candidates for the supported rule targets.

## 4. Relationship To Static Analyzers

certfix complements static analyzers rather than replacing them.

A static analyzer is primarily a diagnostic tool: it reports potential issues.
certfix focuses on the next step: generating a reviewable fixed-code candidate
and related artifacts for an issue candidate.

In a practical workflow, certfix can be used alongside existing tools:

- static analyzers and tests can continue to provide independent signals;
- `certfix check` can be used as an LLM-backed issue-candidate detector;
- `certfix fix` can generate a candidate patch for review;
- CI can use machine-readable reports and exit codes; and
- maintainers can inspect the generated patch and validation result before
  adopting any change.

This design keeps certfix in the repair-assistance layer, not the final authority
layer.

## 5. Why A CLI And Artifact-Based Workflow

certfix is a CLI because a command-line interface fits local development, CI, and
scripted experimentation. It also keeps the tool boundary explicit:

- input is a source file or directory;
- output is a directory of reports, fixed-code candidates, and patches;
- model routes are configured through profiles; and
- failures remain visible as command status, reports, and artifacts.

The main user-facing commands reflect this split:

- `certfix check` detects CERT-C issue candidates and writes reports;
- `certfix fix` generates fixed-code candidates, patches, and validation reports;
- `certfix config` writes bundled profiles; and
- `certfix doctor` checks runtime configuration.

This separation lets users run `check` in a CI-like diagnostic mode and run `fix`
only when they want repair candidates.

## 6. Why Docker-First

certfix moved to a Docker-first public workflow for two reasons.

First, the runtime can be complex. A normal user should not need to manually
recreate the Python environment, CLI entry points, model-route configuration, and
runtime assumptions before trying the tool.

Second, Docker makes data and runtime boundaries easier to understand:

```text
source folder -> /input:ro -> certfix container -> /output
```

The source folder is mounted read-only, and certfix writes reports, fixed-code
candidates, and patches to `/output`. This makes the workflow easier to review
and reduces the risk of accidental source mutation.

Docker does not remove all complexity. Local LLM use still requires an external
`llama-server`, model weights, and compatible GPU/runtime support. However,
Docker makes the certfix side of the workflow reproducible and explicit.

## 7. Why Local, API, And Hybrid Routes

certfix supports local, API, and hybrid model routes because users have different
constraints.

- **Local-only** keeps source code local and avoids provider cost, but requires a
  local model runtime and sufficient hardware. The current public local profile
  uses Qwen3.6-27B MTP through an external OpenAI-compatible `llama-server`, but
  the route is designed to allow the local model profile to change as better
  local models become available.
- **API-only** is easier to try and can use strong hosted models, but source code
  is sent to the configured provider and API cost applies.
- **Hybrid** can keep some steps local while routing other steps to an API
  provider, trading off quality, cost, and data exposure.

The route is not just a performance option. It is a data-boundary decision. For
confidential source code, users must verify which steps are local and which steps
send code or comments to a provider.

## 8. Why Model Routing Is A Management Problem

Model choice in certfix is an engineering-management decision, not only a
benchmark decision.

A stronger hosted model may produce better repair candidates, but it can also
increase API cost, latency, source-code exposure, provider dependence, and
operational opacity. A lower-cost API model may be sufficient for some stages. A
local model may be preferable when source confidentiality, repeat execution cost,
offline use, reproducibility, or model-version control matters. A self-hosted
model on cloud GPU can sit between local hardware and external API providers.
Some cases should still be routed to human review rather than to another model
call.

For this reason, certfix decomposes the workflow into stages and exposes model
routes through profiles. The practical question is not simply "which model is
best?" but "which model, programmatic gate, coding agent, or human reviewer
should handle this stage under this project's quality, cost, latency,
confidentiality, reproducibility, and trust constraints?"

Hosted model APIs are operationally opaque compared with pinned local runtimes.
The same public model name may be affected by upstream model updates, provider
routing, load-related degradation, policy changes, rate limits, pricing changes,
or temporary fallback behavior. For quality-sensitive repair workflows, model
choice is therefore also a reproducibility and availability decision.

certfix keeps model routes explicit in configuration and records outputs as
reviewable artifacts. Local routes can provide stronger control over model
version, runtime, and data boundary, while API routes can provide stronger
capability or lower setup friction. Hybrid routing lets users choose where to
accept API opacity and where to preserve local reproducibility.

## 9. Pipeline Decomposition

certfix is intentionally decomposed into smaller stages rather than asking one
LLM call to detect, identify, repair, validate, and explain everything at once.

At a high level, the workflow is:

```text
C source
  -> comment stripping for LLM-facing analysis
  -> issue-candidate detection
  -> target rule selection
  -> fixed-code candidate generation
  -> validation gates
  -> optional validate-guided retry
  -> reports, patches, and fixed-code candidates
  -> optional comment-merged review artifacts
```

This decomposition has several advantages:

- each step has a narrower task;
- failures are easier to classify;
- validation results can be fed back into one retry attempt;
- reports can show where the workflow succeeded or failed; and
- generated code remains a candidate, not an automatically trusted result.

The workflow is therefore closer to an engineering pipeline than a single prompt.

## 10. Validation Gates

Generated fixed-code candidates are reported as validation-passed by certfix only
when the enabled validation gates pass. This is a workflow status, not a decision
to merge the change. The main gates are:

- **format check**: rejects empty, placeholder, or malformed outputs;
- **compile check**: usually runs the configured C compiler with a syntax-only
  compile mode;
- **target violation removal**: checks whether the selected target rule appears
  to be removed;
- **semantic review**: asks the configured reviewer role whether material
  behavior appears preserved;
- **programmatic regression checks**: blocks known structural regression patterns;
  and
- **retry classification**: decides whether one validate-guided retry is worth
  attempting.

These gates reduce risk. They do not prove semantic equivalence, security
correctness, or target-environment build success.

That distinction is intentional. A validation gate can reject obviously bad or
high-risk candidates, but it should not be presented as a proof of correctness.
The final decision remains with the user's tests, static-analysis workflow, code
review process, and project-specific knowledge.

## 11. Why Retry Is Limited

certfix can perform a validate-guided retry when a candidate fails in a retryable
way. The failure reason is fed back into the repair prompt so the model has a
chance to correct the specific issue.

The retry count is intentionally limited. Repeated retries can increase cost,
latency, and nondeterminism while still failing to resolve the underlying problem.
A small retry budget keeps the workflow predictable and prevents the tool from
masking difficult or unsafe cases behind repeated generation attempts.

If a fix cannot pass the gates after the configured retry path, certfix reports
the failure instead of forcing a patch.

## 12. Why Human Review Remains In The Public Workflow

certfix keeps human review in the current public workflow as an adoption and
governance boundary, not as a claim that AI repair cannot be automated.

A stronger coding agent could consume certfix outputs, including fixed-code
candidates, patches, validation reports, failure reasons, and execution logs,
and attempt revision, explanation, or merge preparation. That is technically
possible. However, full automation depends on project trust, test coverage,
source-code policy, API cost, local model quality, reproducibility requirements,
and responsibility boundaries.

The current public workflow deliberately stops at reviewable artifacts because
users need to build confidence in the detection, repair, validation, and artifact
quality before delegating more of the merge decision to an agent.

This makes certfix model-evolution friendly. As local models, hosted models, and
coding agents improve and become cheaper, the same staged pipeline can route more
work to stronger or cheaper models without changing the basic workflow boundary:
generate candidates, validate them, preserve artifacts, and keep adoption policy
explicit.

A compact autonomy ladder for certfix-style workflows is:

1. diagnostic only;
2. candidate generation;
3. validation-passed candidate;
4. agent-assisted review or retry;
5. gated auto-apply for narrow, well-tested cases; and
6. possible future autonomous repair loops for low-risk code with strong
   project-specific tests.

The current public certfix workflow does not claim autonomous repair or
autonomous merge. It exposes the earlier stages as reviewable artifacts and
keeps the adoption boundary under user control.

## 13. Why Comments Are Removed From The LLM-Facing Path

certfix intentionally removes C comments before the LLM-facing detection, repair,
and validation path where the pipeline uses preprocessed source or fixed-code
candidates. This is not an accidental formatting loss.

Comments can be valuable, but they can also be dangerous inputs for an LLM-backed
repair workflow. They may contain:

- stale intent;
- incorrect explanations;
- disabled code fragments;
- misleading rule hints;
- natural-language summaries that do not match the executable code; or
- hints that make benchmark results look better than the code-only difficulty
  justifies.

Comment-present examples can make model behavior look stronger than the
code-only task because a model may lean on explanatory patterns or rule hints
instead of reasoning from C code structure. That can distort model comparison
and release decisions.

For this reason, the validated path is comment-stripped:

- detection should reason over executable code and rule context;
- repair should produce a code candidate that can compile and validate without
  relying on comments; and
- validation should compare executable structure, not comment text.

## 14. Why Comment-Merge Exists

Although comments are removed from the LLM-facing path, comments are still useful
for human readers. A fixed-code candidate that drops all comments may be harder
to review or merge into a real codebase.

`--comment-merge` addresses this by generating additional comment-merged review
artifacts after the comment-stripped candidate has already passed validation.
This is a final artifact-generation step. It does not reintroduce comments into
check, repair, or validation inputs.

The distinction is important:

- the validated candidate remains the comment-stripped fixed-code file;
- the comment-merged output is a review aid;
- ambiguous comments may be skipped; and
- users should review comment-merged artifacts before adopting them.

## 15. Why Comment-Merge-Audit Is Opt-In

`--comment-merge-audit` adds an LLM audit for restored comments. The purpose is
to suppress comment-merged artifacts when restored comments appear stale,
misleading, or otherwise inconsistent with the fixed code.

This audit is useful, but it has two important caveats.

First, it is still a review aid, not a proof that comments are complete or
correct. Second, it sends the source file's original comments and the restored
comments to the configured review model. If comments contain sensitive
information, users should not enable this path with an API provider unless their
project data policy permits it.

For that reason, comment-merge-audit is explicit opt-in.

## 16. Evaluation Philosophy

certfix's benchmark results should be read as release-quality reference
measurements, not guarantees for arbitrary user code.

The public [benchmark summary](BENCHMARK_SUMMARY.md) reports aggregate results
from a held-out release test set. The evaluation covers Detection F1, Rule hit,
Gold fixed, Safe FP fixed, and Retry success. The test data itself is not
bundled in the package because it is used for release quality checks and has
licensing, dataset-boundary, and evaluation preservation concerns.

The important evaluation principles are:

- keep development/tuning data separate from release evaluation data;
- report aggregate metrics with caveats rather than overclaiming user-code
  performance;
- include safe control cases so false-positive repair behavior is visible;
- evaluate with comments removed from LLM-facing paths to avoid shortcut
  learning; and
- interpret model comparisons together with data-boundary, cost, latency,
  reproducibility, provider stability, and false-positive behavior.

A single success rate is not enough to describe the tool. Detection F1, Rule
hit, Gold fixed, Safe FP fixed, Retry success, latency, cost, reproducibility,
provider stability, and route choice all matter.

## 17. What certfix Does Not Guarantee

certfix intentionally documents its limits.

It does not guarantee:

- complete CERT-C coverage;
- detection of every violation;
- semantic preservation;
- security correctness;
- target-environment build success;
- deterministic LLM output;
- correct repair for multiple independent violations in one function; or
- whole-program analysis.

Current scope boundaries include:

- C only;
- 115 bundled CERT-C rule targets;
- CERT-C recommendations out of scope;
- file/function-scoped analysis rather than whole-program call-graph analysis;
- expected function size is about 200 lines, and functions over about 300 lines
  should be split before repair;
- repair designed for one selected target rule per repair attempt; and
- reviewable artifacts rather than automatic source modification.

These limits are part of the design. They define what users should trust certfix
to do and what they should continue to validate through their own engineering
process.

## 18. How This Fits AI Coding Workflows

certfix is an example of integrating an LLM into a constrained engineering
workflow.

The useful pattern is not simply "ask one model to fix code." The useful pattern
is:

1. define the target rule space;
2. narrow the model task;
3. generate structured outputs;
4. validate the candidate with independent gates;
5. preserve artifacts for human review;
6. route work across local models, API models, programmatic gates, coding agents,
   and human review according to project constraints;
7. keep source mutation explicit and user-controlled; and
8. document the failure modes, data boundaries, and adoption boundaries.

This pattern is relevant beyond CERT-C. AI coding tools need boundaries,
validation, observability, and human-reviewable artifacts if they are going to be
used in quality-sensitive software workflows.

certfix's design is therefore centered on controlled assistance and explicit
adoption policy rather than silent autonomous source modification.

## 19. Summary

certfix is designed around a route-aware principle: model output can be useful
and high quality, but source adoption should remain explicit. The tool converts
model output into reviewable artifacts, runs validation gates, preserves
data/runtime boundaries, and keeps final source adoption under user control.

That is the core rationale behind the CLI design, Docker-first workflow,
local/API/hybrid routing, staged validation, optional retry, comment-stripped
validation path, optional comment-merge artifacts, and explicit limitations.
