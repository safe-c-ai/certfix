# Example Output

This page shows what certfix produces from a small C example. The generated code
is a fixed-code candidate for review; certfix does not edit the original source
file.

## Input

The bundled sample `examples/input/mem30_use_after_free.c` contains a MEM30-C
use-after-free issue candidate:

This example assumes a cloned certfix repository checkout where
`examples/input/` exists. If you installed certfix from PyPI or only pulled the
Docker image, use your own C source file instead.

```c
int run_mem30_demo(void) {
    char *p = make_message("primary", 7);
    if (p == NULL) {
        return -1;
    }

    /* MEM30-C violation: p is freed before print_label uses it. */
    free(p);
    print_label(p);
    return 0;
}
```

## Commands

Run certfix with any configured local or API profile:

```bash
certfix check examples/input/mem30_use_after_free.c --output-dir examples/certfix-output
certfix fix examples/input/mem30_use_after_free.c --output-dir examples/certfix-output
```

## Check Result

`certfix check` writes machine-readable reports under `reports/`:

```text
examples/certfix-output/
`-- reports/
    |-- check.json
    |-- check.sarif
    `-- summary.json
```

The reports identify a MEM30-C issue candidate in the input file. JSON and SARIF
output are intended for tools and CI integrations; text output is intended for
interactive use.

## Fixed-Code Candidate

`certfix fix` writes reviewable fixed-code candidates and patches:

```text
examples/certfix-output/
|-- reports/
|   |-- fixes.json
|   |-- fixes.sarif
|   `-- summary.json
|-- fixes/
|   `-- mem30_use_after_free.fixed.c
`-- patches/
    `-- mem30_use_after_free.c.patch
```

With `certfix fix --comment-merge`, certfix keeps the validated
comment-stripped candidate under `fixes/` and adds review-only comment-merged
artifacts. Use `--comment-merge-audit` when you also want an LLM to suppress
stale or misleading restored comments before those artifacts are written. That
audit sends original/restored comments to the configured review model.

```text
examples/certfix-output/
|-- reports/
|   `-- comment_merge.json
|-- fixes-commented/
|   `-- mem30_use_after_free.fixed.commented.c
`-- patches-commented/
    `-- mem30_use_after_free.c.commented.patch
```

One possible fixed-code candidate is:

```c
int run_mem30_demo(void) {
    char *p = make_message("primary", 7);
    if (p == NULL) {
        return -1;
    }

    print_label(p);
    free(p);
    return 0;
}
```

The corresponding patch is reviewable before applying:

```diff
-    free(p);
     print_label(p);
+    free(p);
     return 0;
```

## Important Caveats

- The exact fixed-code candidate can vary. LLM output is not guaranteed to be
  deterministic across models, providers, prompt profiles, runtime settings, or
  upstream model updates.
- A fixed-code candidate is not a proof of correctness. Validation gates reduce
  risk, but they do not guarantee semantic preservation or security correctness.
- Source files are not modified. Review the generated code and patch before
  merging changes into your project.
- API profiles send source code to the configured provider.
