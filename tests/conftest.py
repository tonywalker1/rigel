"""Shared test fixtures for Rigel tests."""

from __future__ import annotations

import pytest

from rigel.ast import Node
from rigel.parser import parse


def parse_one(source: str) -> Node:
    """Parse a string containing a single expression and return the AST node."""
    nodes = parse(source)
    assert len(nodes) == 1, f"expected 1 node, got {len(nodes)}"
    return nodes[0]
