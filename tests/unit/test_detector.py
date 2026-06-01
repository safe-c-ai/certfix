"""Tests for Detector with function-level chunk splitting."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from certfix.core.detector import Detector, _deduplicate
from certfix.core.include_resolver import IncludeResolver
from certfix.models import Severity, Violation


def _v(rule_id: str = "EXP33-C", line: int = 1) -> Violation:
    return Violation(
        rule_id=rule_id,
        file_path="",
        line=line,
        column=1,
        message="test",
        severity=Severity.ERROR,
    )


class TestDetectorChunking:
    """Tests for Detector.check_file with function-level chunking."""

    def test_single_function_file(self, tmp_path: Path) -> None:
        """Single function file should detect normally."""
        c_file = tmp_path / "test.c"
        c_file.write_text("void foo() {\n    int x;\n    x = 1;\n}")

        backend = MagicMock()
        backend.detect.return_value = [_v("EXP33-C", line=2)]

        detector = Detector(backend)
        result = detector.check_file(c_file)

        assert len(result) == 1
        # line 2 in chunk starting at line 1 → original line 2
        assert result[0].line == 2
        assert result[0].rule_id == "EXP33-C"

    def test_two_functions_with_violations(self, tmp_path: Path) -> None:
        """Violations in different functions get correct line numbers."""
        c_file = tmp_path / "test.c"
        c_file.write_text(
            "void foo() {\n"  # line 1
            "    int x;\n"  # line 2
            "}\n"  # line 3
            "\n"  # line 4
            "void bar() {\n"  # line 5
            "    int *p;\n"  # line 6
            "    *p = 1;\n"  # line 7
            "}"  # line 8
        )

        backend = MagicMock()
        call_count = 0

        def detect_fn(code: str, rules: list[str] | None = None) -> list[Violation]:
            nonlocal call_count
            call_count += 1
            if "foo" in code:
                return [_v("EXP33-C", line=2)]  # chunk-relative line 2
            if "bar" in code:
                return [_v("EXP34-C", line=2)]  # chunk-relative line 2
            return []

        backend.detect.side_effect = detect_fn

        detector = Detector(backend)
        result = detector.check_file(c_file)

        assert len(result) == 2
        # foo: chunk starts at line 1, violation at chunk-relative 2 → line 2
        foo_v = next(v for v in result if v.rule_id == "EXP33-C")
        assert foo_v.line == 2
        # bar: chunk starts at line 5, violation at chunk-relative 2 → line 6
        bar_v = next(v for v in result if v.rule_id == "EXP34-C")
        assert bar_v.line == 6

    def test_line_remapping(self, tmp_path: Path) -> None:
        """Chunk-relative line numbers are remapped to original file lines."""
        c_file = tmp_path / "test.c"
        c_file.write_text(
            "int x = 0;\n"  # line 1 (non-function, becomes context)
            "\n"  # line 2
            "void func() {\n"  # line 3
            "    int bad;\n"  # line 4
            '    printf("%d", bad);\n'  # line 5
            "}"  # line 6
        )

        backend = MagicMock()

        def detect_fn(code: str, rules: list[str] | None = None) -> list[Violation]:
            if "func" in code:
                # Context "int x = 0;" (1 line) + "\n\n" separator
                # Combined: line 1=context, line 2=empty, line 3=func header,
                # line 4=int bad, line 5=printf, line 6=}
                # Report violation at combined line 5 (printf line)
                return [_v("EXP33-C", line=5)]
            return []

        backend.detect.side_effect = detect_fn

        detector = Detector(backend)
        result = detector.check_file(c_file)

        assert len(result) == 1
        # chunk.start_line=3, v.line=5, context_lines=2
        # original = 3 + (5 - 2 - 1) = 5
        assert result[0].line == 5

    def test_fallback_on_no_functions(self, tmp_path: Path) -> None:
        """File with no functions falls back to whole-file detection."""
        c_file = tmp_path / "test.c"
        c_file.write_text("int x = 0;\nint y = 1;\n")

        backend = MagicMock()
        backend.detect.return_value = [_v("DCL30-C", line=1)]

        detector = Detector(backend)
        result = detector.check_file(c_file)

        assert len(result) == 1
        backend.detect.assert_called_once()

    def test_deduplication(self, tmp_path: Path) -> None:
        """Duplicate violations from overlapping context are deduped."""
        violations = [
            _v("EXP33-C", line=5),
            _v("EXP33-C", line=5),  # duplicate
            _v("MEM30-C", line=5),  # different rule, same line
        ]
        result = _deduplicate(violations)
        assert len(result) == 2

    def test_detection_error_in_chunk_continues(self, tmp_path: Path) -> None:
        """Error in one chunk should not stop other chunks."""
        c_file = tmp_path / "test.c"
        c_file.write_text("void foo() {\n    int x;\n}\n\nvoid bar() {\n    int y;\n}")

        backend = MagicMock()
        call_count = 0

        def detect_fn(code: str, rules: list[str] | None = None) -> list[Violation]:
            nonlocal call_count
            call_count += 1
            if "foo" in code:
                raise RuntimeError("model error")
            return [_v("EXP33-C", line=1)]

        backend.detect.side_effect = detect_fn

        detector = Detector(backend)
        result = detector.check_file(c_file)

        # foo errored, bar succeeded
        assert len(result) >= 1

    def test_file_path_set_on_violations(self, tmp_path: Path) -> None:
        """Violations should have file_path set."""
        c_file = tmp_path / "test.c"
        c_file.write_text("void foo() {\n    int x;\n}")

        backend = MagicMock()
        backend.detect.return_value = [_v("EXP33-C", line=1)]

        detector = Detector(backend)
        result = detector.check_file(c_file)

        assert len(result) == 1
        assert result[0].file_path == str(c_file)

    def test_comment_removal_before_splitting(self, tmp_path: Path) -> None:
        """Comments should be removed before splitting."""
        c_file = tmp_path / "test.c"
        c_file.write_text("/* comment with { brace */\nvoid foo() {\n    return;\n}")

        backend = MagicMock()
        backend.detect.return_value = []

        detector = Detector(backend)
        result = detector.check_file(c_file)

        # Should not crash — comment brace handled by preprocessor
        assert result == []

    def test_ignore_directive_works_with_chunks(self, tmp_path: Path) -> None:
        """certfix:ignore should work with chunked detection."""
        c_file = tmp_path / "test.c"
        c_file.write_text("void foo() {\n    int x; // certfix:ignore EXP33-C\n}")

        backend = MagicMock()
        backend.detect.return_value = [_v("EXP33-C", line=2)]

        detector = Detector(backend)
        result = detector.check_file(c_file)

        assert len(result) == 0  # ignored

    def test_header_file_scanned(self, tmp_path: Path) -> None:
        """check_directory should scan .h files."""
        (tmp_path / "main.c").write_text("void foo() {\n    return;\n}")
        (tmp_path / "util.h").write_text(
            "static inline int add(int a, int b) {\n    return a + b;\n}"
        )

        backend = MagicMock()
        backend.detect.return_value = []

        detector = Detector(backend)
        result = detector.check_directory(tmp_path)

        assert result.files_checked == 2

    def test_context_prepended_to_function_chunks(self, tmp_path: Path) -> None:
        """Non-function code should be prepended as context to function chunks."""
        c_file = tmp_path / "test.c"
        c_file.write_text("int buffer[10];\n\nvoid process() {\n    buffer[10] = 0;\n}")

        backend = MagicMock()
        backend.detect.return_value = []

        detector = Detector(backend)
        detector.check_file(c_file)

        # Find the call for the function chunk (should contain context)
        func_call = None
        for call_args in backend.detect.call_args_list:
            code = call_args[0][0]
            if "process" in code:
                func_call = code
                break

        assert func_call is not None
        assert "int buffer[10];" in func_call
        assert "process" in func_call

    def test_non_function_chunk_not_skipped(self, tmp_path: Path) -> None:
        """Non-function chunks should be passed to all backends."""
        c_file = tmp_path / "test.c"
        c_file.write_text("int global = 42;\n\nvoid foo() {\n    return;\n}")

        backend = MagicMock()
        backend.detect.return_value = []

        detector = Detector(backend)
        detector.check_file(c_file)

        # detect should be called for both non-function and function chunks
        assert backend.detect.call_count == 2

    def test_preprocessor_only_chunk_skipped(self, tmp_path: Path) -> None:
        """#include-only preamble chunks should not be detected as source code."""
        c_file = tmp_path / "test.c"
        c_file.write_text("#include <stdio.h>\n\nvoid foo() {\n    return;\n}")

        backend = MagicMock()
        backend.detect.return_value = []

        detector = Detector(backend)
        detector.check_file(c_file)

        backend.detect.assert_called_once()
        assert "foo" in backend.detect.call_args[0][0]

    def test_line_unaware_backend_with_context_maps_to_function_start(
        self, tmp_path: Path
    ) -> None:
        """Line-agnostic classifiers should not discard context-wrapped functions."""
        c_file = tmp_path / "test.c"
        c_file.write_text("#include <stdio.h>\n\nvoid foo() {\n    return;\n}")

        backend = MagicMock()
        backend.line_aware_detection = False
        backend.detect.return_value = [_v("MSC00-C", line=1)]

        detector = Detector(backend)
        result = detector.check_file(c_file)

        assert len(result) == 1
        assert result[0].line == 3

    def test_context_violation_discarded(self, tmp_path: Path) -> None:
        """Violations from prepended context should be discarded."""
        c_file = tmp_path / "test.c"
        c_file.write_text("int bad;\n\nvoid foo() {\n    return;\n}")

        backend = MagicMock()

        def detect_fn(code: str, rules: list[str] | None = None) -> list[Violation]:
            if "foo" in code and "int bad" in code:
                # Report violation at line 1 (context portion)
                return [_v("DCL30-C", line=1)]
            return []

        backend.detect.side_effect = detect_fn

        detector = Detector(backend)
        result = detector.check_file(c_file)

        # Context violation should be discarded (reported via non-function chunk instead)
        foo_violations = [v for v in result if v.rule_id == "DCL30-C" and v.line >= 3]
        assert len(foo_violations) == 0

    def test_only_preceding_context(self, tmp_path: Path) -> None:
        """Only non-function code BEFORE a function should be prepended."""
        c_file = tmp_path / "test.c"
        c_file.write_text(
            "int before = 1;\n\n"
            "void foo() {\n    return;\n}\n\n"
            "int after = 2;\n\n"
            "void bar() {\n    return;\n}"
        )

        backend = MagicMock()
        backend.detect.return_value = []

        detector = Detector(backend)
        detector.check_file(c_file)

        # Find the code passed for foo
        foo_code = None
        bar_code = None
        for call_args in backend.detect.call_args_list:
            code = call_args[0][0]
            if "foo" in code and "bar" not in code:
                foo_code = code
            if "bar" in code and "foo" not in code:
                bar_code = code

        # foo should have "before" but NOT "after"
        if foo_code:
            assert "int before" in foo_code
            assert "int after" not in foo_code

        # bar should have both "before" and "after"
        if bar_code:
            assert "int before" in bar_code
            assert "int after" in bar_code

    def test_header_context_prepended(self, tmp_path: Path) -> None:
        """Header types/macros should be prepended to function chunks."""
        (tmp_path / "types.h").write_text("typedef struct { int x; } Point;\n")
        c_file = tmp_path / "main.c"
        c_file.write_text('#include "types.h"\n\nvoid foo(Point *p) {\n    p->x = 1;\n}')

        backend = MagicMock()
        backend.detect.return_value = []

        resolver = IncludeResolver(project_root=tmp_path)
        detector = Detector(backend, include_resolver=resolver)
        detector.check_file(c_file)

        # Function chunk should have header typedef prepended
        func_call = None
        for call_args in backend.detect.call_args_list:
            code = call_args[0][0]
            if "foo" in code:
                func_call = code
                break

        assert func_call is not None
        assert "Point" in func_call

    def test_negative_line_discarded(self, tmp_path: Path) -> None:
        """Violations with negative remapped lines should be discarded."""
        c_file = tmp_path / "test.c"
        c_file.write_text("int x;\nint y;\n\nvoid foo() {\n    return;\n}")

        backend = MagicMock()

        def detect_fn(code: str, rules: list[str] | None = None) -> list[Violation]:
            if "foo" in code:
                # Report violation at line 1 (in context, not function)
                return [_v("EXP33-C", line=1)]
            return []

        backend.detect.side_effect = detect_fn

        detector = Detector(backend)
        result = detector.check_file(c_file)

        # Should not contain violations with lines before the function
        for v in result:
            assert v.line >= 1
