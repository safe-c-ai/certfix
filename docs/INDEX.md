# certfix Documentation Index

This index lists the public documentation for the certfix v0.2.0 release.
Start with the root [README.md](../README.md) for installation, quick start,
commands, model profiles, limitations, and license information.

## User Documents

| Document | Purpose |
| --- | --- |
| [../README.md](../README.md) | User guide, quick start, commands, profiles, limitations, and license |
| [DOCKER.md](DOCKER.md) | API-only Docker and local Qwen Docker Compose usage |
| [EXAMPLE_OUTPUT.md](EXAMPLE_OUTPUT.md) | Before/after example and generated artifact walkthrough |
| [CONFIGURATION.md](CONFIGURATION.md) | `.certfix.yaml` lookup, bundled profiles, common edits, include paths, advanced routing, and token/context tuning |
| [SUPPORTED_RULES.md](SUPPORTED_RULES.md) | Supported CERT-C rule target catalog and category coverage |
| [QWEN36_MTP_RUNTIME.md](QWEN36_MTP_RUNTIME.md) | Local Qwen3.6-27B MTP `llama-server` setup and runtime notes |
| [BENCHMARK_SUMMARY.md](BENCHMARK_SUMMARY.md) | v0.1.0 release test set results, API cost estimates, and benchmark caveats |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Release-side architecture, check/fix pipelines, validation gates, and scope boundaries |
| [RESEARCH_NOTES.md](RESEARCH_NOTES.md) | Boundary between public release docs and research/archive materials |
| [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | Notices for SARIF, CERT-C metadata, and evaluation dataset boundaries |

## Developer Documents

| Document | Purpose |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Developer setup, local checks, and contribution guidelines |

## Maintainer Release Documents

These documents are public-safe, but they are primarily for maintainers rather
than normal CLI users.

| Document | Purpose |
| --- | --- |
| [MODEL_SMOKE_SUITE.md](MODEL_SMOKE_SUITE.md) | Manual real-model smoke suite for release validation |
| [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) | Release readiness checklist |

## Quick Links

- Installation and requirements: [README.md](../README.md#installation-and-requirements)
- Quick start: [README.md](../README.md#quick-start)
- Docker usage: [DOCKER.md](DOCKER.md)
- Example output: [EXAMPLE_OUTPUT.md](EXAMPLE_OUTPUT.md)
- Commands: [README.md](../README.md#commands)
- Model profiles: [README.md](../README.md#model-profiles)
- Configuration details: [CONFIGURATION.md](CONFIGURATION.md)
- Supported rule catalog: [SUPPORTED_RULES.md](SUPPORTED_RULES.md)
- Local MTP runtime: [QWEN36_MTP_RUNTIME.md](QWEN36_MTP_RUNTIME.md)
- Benchmark caveats: [BENCHMARK_SUMMARY.md](BENCHMARK_SUMMARY.md)

Historical experiment records are not included in the initial public
repository. See [RESEARCH_NOTES.md](RESEARCH_NOTES.md) for the release/research
boundary.
