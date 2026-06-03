"""Tests for preprocessor module."""

from certfix.core.preprocessor import Preprocessor


class TestPreprocessor:
    """Tests for Preprocessor class."""

    def test_remove_line_comment(self) -> None:
        """Test removal of line comments."""
        preprocessor = Preprocessor(keep_comments=False)
        code = "int x = 1;  // comment\nint y = 2;"

        processed, mapping, ignored = preprocessor.process(code)

        assert "// comment" not in processed
        assert "int x = 1;" in processed
        assert "int y = 2;" in processed

    def test_remove_block_comment(self) -> None:
        """Test removal of block comments."""
        preprocessor = Preprocessor(keep_comments=False)
        code = "int x = 1;  /* comment */ int y = 2;"

        processed, mapping, ignored = preprocessor.process(code)

        assert "/* comment */" not in processed
        assert "int x = 1;" in processed
        assert "int y = 2;" in processed

    def test_preserve_line_numbers(self) -> None:
        """Test that line numbers are preserved."""
        preprocessor = Preprocessor(keep_comments=False)
        code = "line1\n// comment\nline3"

        processed, mapping, ignored = preprocessor.process(code)

        lines = processed.split("\n")
        assert len(lines) == 3
        assert mapping.to_original(3) == 3

    def test_extract_ignore_directive(self) -> None:
        """Test extraction of certfix:ignore directives."""
        preprocessor = Preprocessor(keep_comments=False)
        code = "int x;  // certfix:ignore EXP33-C\nint y;"

        processed, mapping, ignored = preprocessor.process(code)

        assert (1, "EXP33-C") in ignored

    def test_extract_ignore_all(self) -> None:
        """Test extraction of certfix:ignore without rule."""
        preprocessor = Preprocessor(keep_comments=False)
        code = "int x;  // certfix:ignore\nint y;"

        processed, mapping, ignored = preprocessor.process(code)

        assert (1, "*") in ignored

    def test_keep_comments_mode(self) -> None:
        """Test that keep_comments=True preserves comments."""
        preprocessor = Preprocessor(keep_comments=True)
        code = "int x;  // comment"

        processed, mapping, ignored = preprocessor.process(code)

        assert processed == code

    def test_multiline_block_comment(self) -> None:
        """Test removal of multiline block comments."""
        preprocessor = Preprocessor(keep_comments=False)
        code = "int x;\n/* line1\nline2 */\nint y;"

        processed, mapping, ignored = preprocessor.process(code)

        assert "line1" not in processed
        assert "line2" not in processed
        lines = processed.split("\n")
        assert len(lines) == 4

    def test_comment_markers_inside_string_literals_are_preserved(self) -> None:
        """String contents should not be treated as comments."""
        preprocessor = Preprocessor(keep_comments=False)
        code = 'printf("http://example.com/a/*not-comment*/b"); // real comment'

        processed, _mapping, _ignored = preprocessor.process(code)

        assert '"http://example.com/a/*not-comment*/b"' in processed
        assert "real comment" not in processed
