# Supported CERT-C Rule Catalog

certfix uses a bundled compact catalog of 115 CERT-C rule targets for
detection, rule selection, repair prompts, validation prompts, and CLI output.

The catalog is not a copy of the CERT-C standard. It contains compact rule
identifiers, titles, categories, and short examples used by certfix. See
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for attribution and
license-boundary notes.

The packaged metadata lives at
[`src/certfix/data/cert_c_rules_with_examples.json`](../src/certfix/data/cert_c_rules_with_examples.json).

## Category Coverage

| Category | Name | Rules |
| --- | --- | ---: |
| PRE | Preprocessor | 3 |
| DCL | Declarations and Initialization | 8 |
| EXP | Expressions | 14 |
| INT | Integers | 7 |
| FLP | Floating Point | 4 |
| ARR | Arrays | 6 |
| STR | Characters and Strings | 6 |
| MEM | Memory Management | 6 |
| FIO | Input Output | 13 |
| ENV | Environment | 5 |
| SIG | Signals | 4 |
| ERR | Error Handling | 3 |
| CON | Concurrency | 12 |
| MSC | Miscellaneous | 8 |
| POS | POSIX | 16 |
| **Total** |  | **115** |

## Rule IDs

This list publishes only rule identifiers, not CERT-C rule text.

| Category | Rule IDs |
| --- | --- |
| PRE | `PRE30-C`, `PRE31-C`, `PRE32-C` |
| DCL | `DCL30-C`, `DCL31-C`, `DCL36-C`, `DCL37-C`, `DCL38-C`, `DCL39-C`, `DCL40-C`, `DCL41-C` |
| EXP | `EXP30-C`, `EXP32-C`, `EXP33-C`, `EXP34-C`, `EXP35-C`, `EXP36-C`, `EXP37-C`, `EXP39-C`, `EXP40-C`, `EXP42-C`, `EXP43-C`, `EXP44-C`, `EXP45-C`, `EXP46-C` |
| INT | `INT30-C`, `INT31-C`, `INT32-C`, `INT33-C`, `INT34-C`, `INT35-C`, `INT36-C` |
| FLP | `FLP30-C`, `FLP32-C`, `FLP34-C`, `FLP36-C` |
| ARR | `ARR30-C`, `ARR32-C`, `ARR36-C`, `ARR37-C`, `ARR38-C`, `ARR39-C` |
| STR | `STR30-C`, `STR31-C`, `STR32-C`, `STR34-C`, `STR37-C`, `STR38-C` |
| MEM | `MEM30-C`, `MEM31-C`, `MEM33-C`, `MEM34-C`, `MEM35-C`, `MEM36-C` |
| FIO | `FIO30-C`, `FIO32-C`, `FIO34-C`, `FIO37-C`, `FIO38-C`, `FIO39-C`, `FIO40-C`, `FIO41-C`, `FIO42-C`, `FIO44-C`, `FIO45-C`, `FIO46-C`, `FIO47-C` |
| ENV | `ENV30-C`, `ENV31-C`, `ENV32-C`, `ENV33-C`, `ENV34-C` |
| SIG | `SIG30-C`, `SIG31-C`, `SIG34-C`, `SIG35-C` |
| ERR | `ERR30-C`, `ERR32-C`, `ERR33-C` |
| CON | `CON30-C`, `CON31-C`, `CON32-C`, `CON33-C`, `CON34-C`, `CON35-C`, `CON36-C`, `CON37-C`, `CON38-C`, `CON39-C`, `CON40-C`, `CON41-C` |
| MSC | `MSC30-C`, `MSC32-C`, `MSC33-C`, `MSC37-C`, `MSC38-C`, `MSC39-C`, `MSC40-C`, `MSC41-C` |
| POS | `POS30-C`, `POS34-C`, `POS35-C`, `POS36-C`, `POS37-C`, `POS38-C`, `POS39-C`, `POS44-C`, `POS47-C`, `POS48-C`, `POS49-C`, `POS50-C`, `POS51-C`, `POS52-C`, `POS53-C`, `POS54-C` |

## How The Catalog Is Used

- `certfix check` uses the catalog to normalize rule candidates and report
  rule IDs/titles.
- `certfix fix` uses the selected target rule and compact rule metadata to
  guide fixed-code candidate generation and validation prompts.
- SARIF and JSON reports use these rule IDs for machine-readable output.

## Limitations

- Supported CERT-C coverage is limited to the 115 bundled rule targets.
  CERT-C recommendations are not supported.
- The catalog defines certfix's public rule target set; it does not
  guarantee that every violation of those rules will be detected or fixed.
- Rule titles and examples are compact prompt/output metadata, not a substitute
  for the official CERT-C rule text.
- Some CERT-C interpretations and environment-specific variants may require
  manual review even when certfix reports a candidate fix.
