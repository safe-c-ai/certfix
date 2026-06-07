# Third-Party Notices

This project is released under the MIT License. Some bundled test fixtures and
metadata refer to third-party standards. These notices preserve attribution and
keep the project license boundary clear.

## SARIF 2.1.0 JSON Schema Fixture

- File: `tests/fixtures/sarif-schema-2.1.0.json`
- Source: OASIS Static Analysis Results Interchange Format (SARIF) Version
  2.1.0 JSON schema.
- Purpose: test fixture for validating SARIF output shape.
- Notice: SARIF is an OASIS standard. Do not treat this schema fixture as
  project-authored MIT code.

## CERT-C Rule Metadata

- File: `src/certfix/data/cert_c_rules_with_examples.json`
- Source context: SEI CERT C Coding Standard rule identifiers and rule titles.
- Purpose: compact rule metadata used for rule-candidate prompts and CLI output.
- Notice: CERT and SEI CERT C are associated with Carnegie Mellon University's
  Software Engineering Institute. The bundled metadata is not a replacement for
  the official CERT-C standard text.

## Evaluation Datasets

Juliet, PrimeVul, calibration, holdout evaluation sample files, and derived
evaluation split metadata are not bundled in public releases.
Maintainer scripts may generate local `*samples.jsonl.gz` files or
`eval-splits/` metadata for maintainer-side benchmarking, but those generated
datasets require separate source, license, and attribution review before public
redistribution.

Juliet reference benchmark summaries may cite aggregate results computed from
the official Juliet C/C++ 1.3 suite, which its official records describe as
public-domain benchmark material. The public repository should not include
Juliet source files or generated Juliet subset manifests unless their source,
license, checksum, and attribution boundaries have been reviewed for the
specific release.

- NIST SARD test suite 112, Juliet C/C++ 1.3:
  `https://samate.nist.gov/SARD/test-suites/112`
- Zenodo record for Juliet Test Suite for C/C++ 1.3:
  `https://zenodo.org/records/4701387`
