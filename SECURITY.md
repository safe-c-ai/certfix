# Security Policy

certfix is an experimental LLM-assisted tool for generating reviewable CERT-C
issue and fixed-code candidates. It does not guarantee security correctness,
behavior equivalence, or complete CERT-C coverage.

## Reporting Security Issues

Do not include private source code, credentials, proprietary code, model outputs
containing secrets, or unpublished evaluation data in public GitHub issues.

For security-sensitive reports, contact the maintainer privately through GitHub
before sharing sensitive details.

## Data Handling

Local profiles keep inference on the configured local server. API profiles send
source code to the configured provider, so confirm your project data policy
before using cloud inference.

Generated reports, fixed-code candidates, and patches should be reviewed before
use in production code.
