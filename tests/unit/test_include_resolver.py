"""Tests for include resolver."""

from pathlib import Path

from certfix.core.include_resolver import IncludeResolver


class TestIncludeResolver:
    """Tests for IncludeResolver."""

    def test_resolves_local_header(self, tmp_path: Path) -> None:
        """Should find header in same directory as source."""
        (tmp_path / "util.h").write_text("typedef int myint;\n")
        source = tmp_path / "main.c"
        source.write_text('#include "util.h"\nvoid foo() {}')

        resolver = IncludeResolver(project_root=tmp_path)
        context = resolver.extract_header_context(source, source.read_text())

        assert "typedef int myint" in context

    def test_resolves_from_include_dirs(self, tmp_path: Path) -> None:
        """Should find header in configured include_dirs."""
        inc_dir = tmp_path / "include"
        inc_dir.mkdir()
        (inc_dir / "types.h").write_text("struct Point { int x; int y; };\n")

        source = tmp_path / "src" / "main.c"
        source.parent.mkdir()
        source.write_text('#include "types.h"\nvoid foo() {}')

        resolver = IncludeResolver(include_dirs=[str(inc_dir)], project_root=tmp_path)
        context = resolver.extract_header_context(source, source.read_text())

        assert "struct Point" in context

    def test_ignores_system_headers(self, tmp_path: Path) -> None:
        """System headers (<...>) should not be resolved."""
        source = tmp_path / "main.c"
        source.write_text("#include <stdio.h>\nvoid foo() {}")

        resolver = IncludeResolver(project_root=tmp_path)
        context = resolver.extract_header_context(source, source.read_text())

        assert context == ""

    def test_ignores_missing_headers(self, tmp_path: Path) -> None:
        """Missing headers should be silently ignored."""
        source = tmp_path / "main.c"
        source.write_text('#include "nonexistent.h"\nvoid foo() {}')

        resolver = IncludeResolver(project_root=tmp_path)
        context = resolver.extract_header_context(source, source.read_text())

        assert context == ""

    def test_extracts_only_non_function_code(self, tmp_path: Path) -> None:
        """Should extract typedefs/macros but not function bodies."""
        (tmp_path / "util.h").write_text(
            "#define MAX 100\n\n"
            "typedef int myint;\n\n"
            "static inline int add(int a, int b) {\n"
            "    return a + b;\n"
            "}\n"
        )
        source = tmp_path / "main.c"
        source.write_text('#include "util.h"\nvoid foo() {}')

        resolver = IncludeResolver(project_root=tmp_path)
        context = resolver.extract_header_context(source, source.read_text())

        assert "#define MAX 100" in context or "MAX" in context
        assert "typedef int myint" in context
        assert "return a + b" not in context

    def test_caches_header_results(self, tmp_path: Path) -> None:
        """Same header should be read only once."""
        (tmp_path / "util.h").write_text("typedef int myint;\n")

        resolver = IncludeResolver(project_root=tmp_path)

        source1 = tmp_path / "a.c"
        source1.write_text('#include "util.h"\nvoid a() {}')
        source2 = tmp_path / "b.c"
        source2.write_text('#include "util.h"\nvoid b() {}')

        ctx1 = resolver.extract_header_context(source1, source1.read_text())
        ctx2 = resolver.extract_header_context(source2, source2.read_text())

        assert ctx1 == ctx2
        # Cache should have exactly 1 entry
        assert len(resolver._cache) == 1

    def test_blocks_path_traversal(self, tmp_path: Path) -> None:
        """Paths outside project root should be blocked."""
        source = tmp_path / "main.c"
        source.write_text('#include "../../etc/passwd"\nvoid foo() {}')

        resolver = IncludeResolver(project_root=tmp_path)
        context = resolver.extract_header_context(source, source.read_text())

        assert context == ""

    def test_multiple_headers(self, tmp_path: Path) -> None:
        """Multiple includes should all be resolved."""
        (tmp_path / "types.h").write_text("typedef int myint;\n")
        (tmp_path / "config.h").write_text("#define MAX 100\n")

        source = tmp_path / "main.c"
        source.write_text('#include "types.h"\n#include "config.h"\nvoid foo() {}')

        resolver = IncludeResolver(project_root=tmp_path)
        context = resolver.extract_header_context(source, source.read_text())

        assert "typedef int myint" in context
        assert "MAX" in context

    def test_no_duplicate_headers(self, tmp_path: Path) -> None:
        """Same header included twice should only appear once."""
        (tmp_path / "util.h").write_text("typedef int myint;\n")

        source = tmp_path / "main.c"
        source.write_text('#include "util.h"\n#include "util.h"\nvoid foo() {}')

        resolver = IncludeResolver(project_root=tmp_path)
        context = resolver.extract_header_context(source, source.read_text())

        assert context.count("typedef int myint") == 1
