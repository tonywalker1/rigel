"""Tests for the Rigel lexer."""

from __future__ import annotations

import pytest

from rigel.common import LexError
from rigel.lexer import Token, TokenKind, tokenize


class TestAtoms:
    """Tokenization of atomic values."""

    def test_integer(self):
        tokens = tokenize("42")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.INT
        assert tokens[0].text == "42"

    def test_negative_integer(self):
        tokens = tokenize("-7")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.INT
        assert tokens[0].text == "-7"

    def test_zero(self):
        tokens = tokenize("0")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.INT

    def test_integer_with_suffix(self):
        tokens = tokenize("42:int8")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.INT
        assert tokens[0].text == "42:int8"

    def test_float(self):
        tokens = tokenize("3.14")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.FLOAT
        assert tokens[0].text == "3.14"

    def test_negative_float(self):
        tokens = tokenize("-0.5")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.FLOAT

    def test_float_with_suffix(self):
        tokens = tokenize("3.14:float32")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.FLOAT
        assert tokens[0].text == "3.14:float32"

    def test_string(self):
        tokens = tokenize('"hello"')
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.STRING
        assert tokens[0].text == '"hello"'

    def test_string_with_escapes(self):
        tokens = tokenize(r'"with \"escapes\""')
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.STRING

    def test_multiline_string(self):
        tokens = tokenize('"line1\nline2"')
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.STRING

    def test_bool_true(self):
        tokens = tokenize("true")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.BOOL
        assert tokens[0].text == "true"

    def test_bool_false(self):
        tokens = tokenize("false")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.BOOL
        assert tokens[0].text == "false"

    def test_symbol(self):
        tokens = tokenize("x")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.SYMBOL
        assert tokens[0].text == "x"

    def test_symbol_operator(self):
        tokens = tokenize("+")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.SYMBOL
        assert tokens[0].text == "+"

    def test_symbol_hyphenated(self):
        tokens = tokenize("my-func")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.SYMBOL

    def test_symbol_arrow(self):
        tokens = tokenize("->")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.SYMBOL

    def test_symbol_gte(self):
        tokens = tokenize(">=")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.SYMBOL

    def test_keyword(self):
        tokens = tokenize(":args")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.KEYWORD
        assert tokens[0].text == ":args"

    def test_keyword_with(self):
        tokens = tokenize(":with")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.KEYWORD

    def test_keyword_capture(self):
        tokens = tokenize(":capture")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.KEYWORD


class TestStructure:
    """Tokenization of structural elements."""

    def test_simple_expr(self):
        tokens = tokenize("(+ 1 2)")
        kinds = [t.kind for t in tokens]
        assert kinds == [TokenKind.LPAREN, TokenKind.SYMBOL, TokenKind.INT, TokenKind.INT, TokenKind.RPAREN]

    def test_empty_parens(self):
        tokens = tokenize("()")
        kinds = [t.kind for t in tokens]
        assert kinds == [TokenKind.LPAREN, TokenKind.RPAREN]

    def test_nested_parens(self):
        tokens = tokenize("(())")
        kinds = [t.kind for t in tokens]
        assert kinds == [TokenKind.LPAREN, TokenKind.LPAREN, TokenKind.RPAREN, TokenKind.RPAREN]

    def test_brackets(self):
        tokens = tokenize("[x]")
        kinds = [t.kind for t in tokens]
        assert kinds == [TokenKind.LBRACKET, TokenKind.SYMBOL, TokenKind.RBRACKET]

    def test_comment_stripped(self):
        tokens = tokenize("; comment\n42")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.INT
        assert tokens[0].text == "42"

    def test_only_comment(self):
        tokens = tokenize("; just a comment")
        assert len(tokens) == 0

    def test_whitespace_variations(self):
        tokens = tokenize("(+\t1\n  2)")
        kinds = [t.kind for t in tokens]
        assert kinds == [TokenKind.LPAREN, TokenKind.SYMBOL, TokenKind.INT, TokenKind.INT, TokenKind.RPAREN]


class TestSpans:
    """Source location tracking."""

    def test_single_token_span(self):
        tokens = tokenize("hello")
        assert tokens[0].span.line == 1
        assert tokens[0].span.col == 1
        assert tokens[0].span.offset == 0
        assert tokens[0].span.length == 5

    def test_multi_token_positions(self):
        tokens = tokenize("(+ 1 2)")
        assert tokens[0].span.col == 1   # (
        assert tokens[1].span.col == 2   # +
        assert tokens[2].span.col == 4   # 1
        assert tokens[3].span.col == 6   # 2
        assert tokens[4].span.col == 7   # )

    def test_multiline_tracking(self):
        tokens = tokenize("foo\nbar\nbaz")
        assert tokens[0].span.line == 1
        assert tokens[1].span.line == 2
        assert tokens[2].span.line == 3

    def test_filename(self):
        tokens = tokenize("x", filename="test.rgl")
        assert tokens[0].span.file == "test.rgl"


class TestQualifierMerge:
    """Qualifier suffix merging into numeric literals."""

    def test_int_with_unsigned(self):
        tokens = tokenize("255:int16 unsigned")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.INT
        assert tokens[0].text == "255:int16 unsigned"

    def test_int_with_multiple_qualifiers(self):
        tokens = tokenize("42:int32 unsigned unchecked")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.INT
        assert tokens[0].text == "42:int32 unsigned unchecked"

    def test_float_with_unchecked(self):
        tokens = tokenize("3.14:float64 unchecked")
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.FLOAT
        assert tokens[0].text == "3.14:float64 unchecked"

    def test_no_merge_without_suffix(self):
        # Plain number followed by symbol — no merge
        tokens = tokenize("42 unsigned")
        assert len(tokens) == 2
        assert tokens[0].kind == TokenKind.INT
        assert tokens[0].text == "42"
        assert tokens[1].kind == TokenKind.SYMBOL
        assert tokens[1].text == "unsigned"

    def test_no_merge_with_non_qualifier(self):
        # Number with suffix followed by non-qualifier symbol
        tokens = tokenize("42:int16 foo")
        assert len(tokens) == 2
        assert tokens[0].text == "42:int16"
        assert tokens[1].text == "foo"

    def test_qualifier_span_covers_all(self):
        tokens = tokenize("255:int16 unsigned")
        # Span should cover from '2' to 'd' (full "255:int16 unsigned")
        assert tokens[0].span.offset == 0
        assert tokens[0].span.length == len("255:int16 unsigned")

    def test_in_expression_context(self):
        # Qualifier merge should work inside parentheses
        tokens = tokenize("(let x 255:int16 unsigned)")
        kinds = [t.kind for t in tokens]
        assert kinds == [TokenKind.LPAREN, TokenKind.SYMBOL, TokenKind.SYMBOL,
                         TokenKind.INT, TokenKind.RPAREN]
        assert tokens[3].text == "255:int16 unsigned"


class TestErrors:
    """Lexer error handling."""

    def test_unterminated_string(self):
        with pytest.raises(LexError, match="unterminated string"):
            tokenize('"unterminated')

    def test_invalid_number(self):
        with pytest.raises(LexError, match="invalid numeric"):
            tokenize("12.34.56")
