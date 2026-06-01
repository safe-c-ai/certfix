"""Tests for C source file splitter."""

from certfix.core.splitter import split_functions


class TestSplitFunctions:
    """Tests for split_functions."""

    def test_single_function(self) -> None:
        code = "int main() {\n    return 0;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].name == "main"
        assert funcs[0].start_line == 1
        assert funcs[0].end_line == 3

    def test_two_functions(self) -> None:
        code = "void foo() {\n    return;\n}\n\nint bar() {\n    return 1;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 2
        assert funcs[0].name == "foo"
        assert funcs[1].name == "bar"

    def test_preamble_before_function(self) -> None:
        code = "#include <stdio.h>\n\nint x = 0;\n\nvoid foo() {\n    x++;\n}"
        chunks = split_functions(code)
        non_funcs = [c for c in chunks if not c.is_function]
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert len(non_funcs) >= 1
        assert "#include" in non_funcs[0].code

    def test_trailing_code_after_function(self) -> None:
        code = "void foo() {\n}\n\nint global = 42;"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        non_funcs = [c for c in chunks if not c.is_function]
        assert len(funcs) == 1
        assert any("global" in c.code for c in non_funcs)

    def test_nested_braces(self) -> None:
        code = (
            "void foo() {\n"
            "    if (1) {\n"
            "        for (int i = 0; i < 10; i++) {\n"
            "            x++;\n"
            "        }\n"
            "    }\n"
            "}"
        )
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].name == "foo"
        assert funcs[0].end_line == 7

    def test_multiline_signature(self) -> None:
        code = "int\nfoo(int a,\n    int b)\n{\n    return a + b;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].name == "foo"

    def test_static_function(self) -> None:
        code = "static int helper(void) {\n    return 0;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].name == "helper"

    def test_inline_function(self) -> None:
        code = "inline void fast(void) {\n    return;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].name == "fast"

    def test_pointer_return_type(self) -> None:
        code = 'char *get_name(void) {\n    return "hello";\n}'
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].name == "get_name"

    def test_string_with_braces(self) -> None:
        code = 'void foo() {\n    printf("{ }\\n");\n}'
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].end_line == 3

    def test_empty_file(self) -> None:
        chunks = split_functions("")
        assert len(chunks) == 0

    def test_no_functions(self) -> None:
        code = "#include <stdio.h>\nint x = 0;\n"
        chunks = split_functions(code)
        assert all(not c.is_function for c in chunks)

    def test_unbalanced_braces_returns_empty(self) -> None:
        code = "void foo() {\n    if (1) {\n"
        chunks = split_functions(code)
        assert chunks == []

    def test_line_numbers_correct(self) -> None:
        code = (
            "#include <stdio.h>\n"  # line 1
            "\n"  # line 2
            "void foo() {\n"  # line 3
            "    int x = 0;\n"  # line 4
            "}\n"  # line 5
            "\n"  # line 6
            "int bar() {\n"  # line 7
            "    return 1;\n"  # line 8
            "}"  # line 9
        )
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 2
        assert funcs[0].start_line == 3
        assert funcs[0].end_line == 5
        assert funcs[1].start_line == 7
        assert funcs[1].end_line == 9

    def test_brace_on_next_line(self) -> None:
        code = "void foo()\n{\n    return;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].name == "foo"

    def test_declaration_not_matched(self) -> None:
        """Function declarations (with ;) should not be matched."""
        code = "void foo(int x);\n\nvoid bar() {\n    return;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].name == "bar"

    def test_struct_inside_function(self) -> None:
        code = "void foo() {\n    struct {\n        int x;\n    } s;\n    s.x = 1;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert funcs[0].end_line == 6

    def test_chunk_code_content(self) -> None:
        """Chunk code should contain the actual function text."""
        code = "int add(int a, int b) {\n    return a + b;\n}"
        chunks = split_functions(code)
        funcs = [c for c in chunks if c.is_function]
        assert len(funcs) == 1
        assert "return a + b" in funcs[0].code
