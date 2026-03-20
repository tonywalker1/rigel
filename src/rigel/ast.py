"""AST node definitions for Rigel.

Every node is a frozen dataclass carrying a Span for source location.
Nodes are pure data — traversal is done externally.
"""

from __future__ import annotations

from dataclasses import dataclass

from rigel.common import Span


# --- Atoms (leaf nodes) ---

@dataclass(frozen=True)
class IntLiteral:
    value: int
    type_suffix: str | None     # e.g. "int8", "int16 unsigned"
    span: Span


@dataclass(frozen=True)
class FloatLiteral:
    value: float
    type_suffix: str | None
    span: Span


@dataclass(frozen=True)
class StringLiteral:
    value: str
    span: Span


@dataclass(frozen=True)
class BoolLiteral:
    value: bool
    span: Span


@dataclass(frozen=True)
class Symbol:
    name: str
    span: Span


# --- Core forms (compound nodes) ---

@dataclass(frozen=True)
class LetForm:
    name: Symbol
    value: Node
    type_ann: Node | None
    mutable: bool
    span: Span


@dataclass(frozen=True)
class SetForm:
    name: Symbol
    value: Node
    span: Span


@dataclass(frozen=True)
class LambdaForm:
    params: list[Param]
    captures: list[Capture]
    return_type: Node | None
    effects: list[Symbol]
    body: list[Node]
    span: Span


@dataclass(frozen=True)
class Param:
    name: Symbol
    type_ann: Node
    default: Node | None
    span: Span


@dataclass(frozen=True)
class Capture:
    name: Symbol
    mut: bool
    span: Span


@dataclass(frozen=True)
class TypeForm:
    fields: list[Field]
    invariant: Node | None
    constructor: Node | None
    viewer: Node | None
    release: Node | None
    span: Span


@dataclass(frozen=True)
class Field:
    name: Symbol
    type_ann: Node
    mut: bool
    span: Span


@dataclass(frozen=True)
class IfForm:
    condition: Node
    then_branch: Node
    else_branch: Node | None
    span: Span


@dataclass(frozen=True)
class CondForm:
    clauses: list[tuple[Node, Node]]
    else_clause: Node | None
    span: Span


@dataclass(frozen=True)
class MatchForm:
    target: Node
    arms: list[MatchArm]
    span: Span


@dataclass(frozen=True)
class MatchArm:
    pattern: Node
    guard: Node | None
    body: Node
    span: Span


@dataclass(frozen=True)
class CallForm:
    func: Node
    args: list[Node]
    span: Span


@dataclass(frozen=True)
class DoForm:
    body: list[Node]
    span: Span


@dataclass(frozen=True)
class ModuleForm:
    name: Symbol
    exports: list[Symbol]
    body: list[Node]
    span: Span


@dataclass(frozen=True)
class ImportForm:
    module: Symbol
    names: list[Symbol] | None
    alias: Symbol | None
    span: Span


@dataclass(frozen=True)
class ConstraintForm:
    params: list[Symbol]
    requirements: list[Node]
    span: Span


@dataclass(frozen=True)
class HandleForm:
    body: Node
    handlers: list[HandlerClause]
    span: Span


@dataclass(frozen=True)
class HandlerClause:
    effect: Symbol
    params: list[Param]
    body: Node
    resume: Symbol | None
    span: Span


@dataclass(frozen=True)
class RaiseForm:
    effect: Symbol
    args: list[Node]
    span: Span


# Union type for all nodes — pattern match via `match` statement
Node = (
    IntLiteral | FloatLiteral | StringLiteral | BoolLiteral | Symbol
    | LetForm | SetForm | LambdaForm | TypeForm
    | IfForm | CondForm | MatchForm | CallForm | DoForm
    | ModuleForm | ImportForm | ConstraintForm
    | HandleForm | RaiseForm
)
