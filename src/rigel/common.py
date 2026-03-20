"""Shared types: source spans and error classes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """Source location for a token or AST node."""

    file: str       # source file path
    line: int       # 1-based
    col: int        # 1-based
    offset: int     # 0-based byte offset into source
    length: int     # byte length of the token/node

    def __repr__(self) -> str:
        return f"Span({self.file}:{self.line}:{self.col})"

    def to(self, other: Span) -> Span:
        """Return a span covering from self to other (inclusive)."""
        end = other.offset + other.length
        return Span(
            file=self.file,
            line=self.line,
            col=self.col,
            offset=self.offset,
            length=end - self.offset,
        )


class RigelError(Exception):
    """Base class for all Rigel errors."""

    def __init__(self, message: str, span: Span) -> None:
        self.message = message
        self.span = span
        super().__init__(f"{span.file}:{span.line}:{span.col}: {message}")


class LexError(RigelError):
    """Error during tokenization."""


class ParseError(RigelError):
    """Error during parsing."""


class TypeError_(RigelError):
    """Error during type checking.

    Named TypeError_ to avoid shadowing the built-in TypeError.
    """


class EffectError(RigelError):
    """Error during effect checking."""


class NameError_(RigelError):
    """Error for unresolved names.

    Named NameError_ to avoid shadowing the built-in NameError.
    """


class RuntimeError_(RigelError):
    """Error during interpretation (division by zero, unhandled effect, etc.)."""


class RigelEffect(Exception):
    """Raised (as Python exception) when a Rigel effect is raised.

    Not a RigelError — it's a control-flow mechanism, not a user-facing error.
    """

    def __init__(self, effect: str, effect_args: list, span: Span) -> None:
        self.effect = effect
        self.effect_args = effect_args
        self.span = span
        super().__init__(f"effect raised: {effect}")
