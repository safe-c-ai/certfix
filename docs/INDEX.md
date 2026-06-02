# certfix Documentation Index

This index lists the public documentation for the current certfix release.
Start with the root [README.md](../README.md) for runtime selection, getting
started commands, model routes, limitations, and license information.

## User Documents

| Document | Purpose |
| --- | --- |
| [../README.md](../README.md) | User guide, runtime selection, getting started commands, model routes, limitations, and license |
| [DOCKER.md](DOCKER.md) | API-only, local `llama-server`, and hybrid Docker usage |
| [INSTALLATION.md](INSTALLATION.md) | Manual installation, compiler setup, local `llama-server` setup, and non-Docker examples |
| [EXAMPLE_OUTPUT.md](EXAMPLE_OUTPUT.md) | Before/after example and generated artifact walkthrough |
| [CONFIGURATION.md](CONFIGURATION.md) | `.certfix.yaml` lookup, bundled profiles, common edits, include paths, advanced routing, and token/context tuning |
| [LIMITATIONS.md](LIMITATIONS.md) | Full scope, repair, validation, and runtime limitations |
| [SUPPORTED_RULES.md](SUPPORTED_RULES.md) | Supported CERT-C rule target catalog and category coverage |
| [QWEN36_MTP_RUNTIME.md](QWEN36_MTP_RUNTIME.md) | Local Qwen3.6-27B MTP `llama-server` setup and runtime notes |
| [BENCHMARK_SUMMARY.md](BENCHMARK_SUMMARY.md) | release test set results, API cost estimates, and benchmark caveats |
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

- Getting started: [README.md](../README.md#1-getting-started)
- Manual installation and requirements: [INSTALLATION.md](INSTALLATION.md)
- Docker usage: [DOCKER.md](DOCKER.md)
- Example output: [EXAMPLE_OUTPUT.md](EXAMPLE_OUTPUT.md)
- Commands: [README.md](../README.md#31-certfix-docker)
- Model routes: [README.md](../README.md#33-model-routes-and-configuration)
- Configuration details: [CONFIGURATION.md](CONFIGURATION.md)
- Limitations: [LIMITATIONS.md](LIMITATIONS.md)
- Supported rule catalog: [SUPPORTED_RULES.md](SUPPORTED_RULES.md)
- Local MTP runtime: [QWEN36_MTP_RUNTIME.md](QWEN36_MTP_RUNTIME.md)
- Benchmark caveats: [BENCHMARK_SUMMARY.md](BENCHMARK_SUMMARY.md)

Historical experiment records are not included in the initial public
repository. See [RESEARCH_NOTES.md](RESEARCH_NOTES.md) for the release/research
boundary.
