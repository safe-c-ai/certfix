"""Tests for release programmatic semantic-risk checks."""

from certfix.core.programmatic_checks import run_programmatic_checks


def check_ids(
    *,
    original_code: str,
    fixed_code: str,
    rule_id: str,
    preset: str = "release_v1",
) -> list[str]:
    findings = run_programmatic_checks(
        original_code=original_code,
        fixed_code=fixed_code,
        rule_id=rule_id,
        preset=preset,
    )

    return [finding.check_id for finding in findings]


def test_release_v1_excludes_same_resource_early_return() -> None:
    findings = run_programmatic_checks(
        original_code="void f(lock_t *a, lock_t *b) { lock(a); lock(b); }",
        fixed_code="void f(lock_t *a, lock_t *b) { if (a == b) return; lock(a); lock(b); }",
        rule_id="POS51-C",
    )

    assert [finding.check_id for finding in findings] == []


def test_exp44_sizeof_side_effect_materialized_blocks() -> None:
    findings = run_programmatic_checks(
        original_code="void f(int i) { size_t n = sizeof(i++); }",
        fixed_code="void f(int i) { i++; size_t n = sizeof(i); }",
        rule_id="EXP44-C",
    )

    assert [finding.check_id for finding in findings] == ["exp44_sizeof_side_effect_materialized"]
    assert findings[0].rule_id == "EXP44-C"


def test_candidate_no_signal_flags_same_resource_early_return_added() -> None:
    ids = check_ids(
        original_code="void f(lock_t *a, lock_t *b) { lock(a); lock(b); }",
        fixed_code="void f(lock_t *a, lock_t *b) { if (a == b) return; lock(a); lock(b); }",
        rule_id="POS51-C",
        preset="candidate_no_signal_v1",
    )

    assert ids == ["same_resource_early_return_added"]


def test_candidate_no_signal_allows_existing_same_resource_early_return() -> None:
    code = "void f(lock_t *a, lock_t *b) { if (a == b) return; lock(a); lock(b); }"

    assert (
        check_ids(
            original_code=code,
            fixed_code=code,
            rule_id="POS51-C",
            preset="candidate_no_signal_v1",
        )
        == []
    )


def test_visible_output_literal_change_blocks_con35_output_change() -> None:
    ids = check_ids(
        original_code='void f(void) { printf("locked\\n"); }',
        fixed_code='void f(void) { printf("skipped\\n"); }',
        rule_id="CON35-C",
    )

    assert ids == ["visible_output_literal_change"]


def test_visible_output_literal_change_allows_same_literal() -> None:
    assert (
        check_ids(
            original_code='void f(void) { printf("locked\\n"); }',
            fixed_code='void f(void) { printf("locked\\n"); }',
            rule_id="CON35-C",
        )
        == []
    )


def test_visible_output_literal_change_ignores_unrelated_rules() -> None:
    assert (
        check_ids(
            original_code='void f(void) { printf("old\\n"); }',
            fixed_code='void f(void) { printf("new\\n"); }',
            rule_id="EXP44-C",
        )
        == []
    )


def test_pos51_raw_pointer_order_blocks_relational_lock_ordering() -> None:
    ids = check_ids(
        original_code=(
            "void f(lock_t *a, lock_t *b) { "
            "pthread_mutex_lock(a); pthread_mutex_lock(b); }"
        ),
        fixed_code="""
            void f(lock_t *a, lock_t *b) {
                if (a < b) {
                    pthread_mutex_lock(a);
                    pthread_mutex_lock(b);
                }
            }
        """,
        rule_id="POS51-C",
    )

    assert ids == ["pos51_raw_pointer_order"]


def test_pos51_raw_pointer_order_allows_defined_key_ordering() -> None:
    assert (
        check_ids(
            original_code=(
                "void f(node_t *a, node_t *b) { "
                "pthread_mutex_lock(&a->mu); pthread_mutex_lock(&b->mu); }"
            ),
            fixed_code="""
                void f(node_t *a, node_t *b) {
                    if (a->id < b->id) {
                        pthread_mutex_lock(&a->mu);
                        pthread_mutex_lock(&b->mu);
                    }
                }
            """,
            rule_id="POS51-C",
        )
        == []
    )


def test_exp45_assignment_replaced_by_comparison_blocks_removed_update() -> None:
    ids = check_ids(
        original_code="int f(void) { int rc; if (rc = read_status()) return rc; return 0; }",
        fixed_code="int f(void) { int rc; if (rc == read_status()) return rc; return 0; }",
        rule_id="EXP45-C",
    )

    assert ids == ["exp45_assignment_replaced_by_comparison"]


def test_exp45_assignment_replaced_by_comparison_allows_preserved_assignment() -> None:
    assert (
        check_ids(
            original_code="int f(void) { int rc; if (rc = read_status()) return rc; return 0; }",
            fixed_code=(
                "int f(void) { int rc; "
                "if ((rc = read_status()) == 0) return rc; return 0; }"
            ),
            rule_id="EXP45-C",
        )
        == []
    )


def test_exp44_sizeof_pointer_to_pointee_blocks_with_side_effect_operand() -> None:
    ids = check_ids(
        original_code="void f(int *p) { size_t n = sizeof(p++); }",
        fixed_code="void f(int *p) { size_t n = sizeof(*p); }",
        rule_id="EXP44-C",
    )

    assert ids == ["exp44_sizeof_pointer_to_pointee"]


def test_exp44_sizeof_checks_ignore_operands_without_side_effects() -> None:
    assert (
        check_ids(
            original_code="void f(int *p) { size_t n = sizeof(p); }",
            fixed_code="void f(int *p) { size_t n = sizeof(*p); }",
            rule_id="EXP44-C",
        )
        == []
    )


def test_exp46_toggle_update_replaced_blocks_fixed_boolean_assignment() -> None:
    ids = check_ids(
        original_code="void f(unsigned flags) { flags ^= MASK; }",
        fixed_code="void f(unsigned flags) { flags = 0; }",
        rule_id="EXP46-C",
    )

    assert ids == ["exp46_toggle_update_replaced"]


def test_exp46_complement_to_logical_not_blocks_operator_change() -> None:
    ids = check_ids(
        original_code="int f(unsigned flags) { return ~flags; }",
        fixed_code="int f(unsigned flags) { return !flags; }",
        rule_id="EXP46-C",
    )

    assert ids == ["exp46_bitwise_complement_to_logical_not"]


def test_exp46_checks_allow_preserved_bitwise_operations() -> None:
    assert (
        check_ids(
            original_code="void f(unsigned flags) { flags ^= MASK; int x = ~flags; }",
            fixed_code="void f(unsigned flags) { flags ^= MASK; int x = ~flags; }",
            rule_id="EXP46-C",
        )
        == []
    )


def test_env33_exec_argv_shift_blocks_passing_original_argv() -> None:
    ids = check_ids(
        original_code='int f(char **argv) { return system("ls -l"); }',
        fixed_code="int f(char **argv) { return execvp(argv[0], argv); }",
        rule_id="ENV33-C",
    )

    assert ids == ["env33_exec_argv_shift"]


def test_env33_exec_argv_shift_allows_explicit_argument_vector() -> None:
    assert (
        check_ids(
            original_code='int f(void) { return system("ls -l"); }',
            fixed_code=(
                'int f(void) { char *args[] = {"ls", "-l", NULL}; '
                "return execvp(args[0], args); }"
            ),
            rule_id="ENV33-C",
        )
        == []
    )


def test_con40_atomic_freshness_blocks_collapsed_repeated_loads() -> None:
    ids = check_ids(
        original_code="""
            int f(void) {
                int before = atomic_load(&ready);
                int after = atomic_load(&ready);
                return before != after;
            }
        """,
        fixed_code="""
            int f(void) {
                int ready_snapshot = atomic_load(&ready);
                return ready_snapshot != ready_snapshot;
            }
        """,
        rule_id="CON40-C",
    )

    assert ids == ["con40_atomic_freshness_collapsed"]


def test_con40_atomic_freshness_allows_preserved_repeated_loads() -> None:
    assert (
        check_ids(
            original_code="int f(void) { return atomic_load(&ready) == atomic_load(&ready); }",
            fixed_code="int f(void) { return atomic_load(&ready) == atomic_load(&ready); }",
            rule_id="CON40-C",
        )
        == []
    )


def test_mem36_copy_size_mismatch_blocks_unclamped_old_size_copy() -> None:
    ids = check_ids(
        original_code=(
            "void *f(void *old_buf, size_t old_size) { "
            "return realloc(old_buf, old_size); }"
        ),
        fixed_code="""
            void *f(void *old_buf, size_t old_size) {
                void *new_buf = aligned_alloc(64, old_size);
                memcpy(new_buf, old_buf, old_size);
                return new_buf;
            }
        """,
        rule_id="MEM36-C",
    )

    assert ids == ["mem36_unclamped_memcpy_after_aligned_alloc"]


def test_mem36_copy_size_mismatch_allows_new_size_clamp() -> None:
    assert (
        check_ids(
            original_code=(
                "void *f(void *old_buf, size_t old_size, size_t new_size) { "
                "return realloc(old_buf, new_size); }"
            ),
            fixed_code="""
                void *f(void *old_buf, size_t old_size, size_t new_size) {
                    void *new_buf = aligned_alloc(64, new_size);
                    memcpy(new_buf, old_buf, min(old_size, new_size));
                    return new_buf;
                }
            """,
            rule_id="MEM36-C",
        )
        == []
    )
