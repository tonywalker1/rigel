"""Parser for Rigel source text.

Two-pass approach:
1. S-expression pass: tokens → nested lists (generic s-expression structure)
2. Form recognition pass: nested lists → typed AST nodes
"""

from __future__ import annotations

from rigel.ast import (
    BoolLiteral,
    CallForm,
    Capture,
    CondForm,
    ConstraintForm,
    DoForm,
    Field,
    HandleForm,
    HandlerClause,
    IfForm,
    ImportForm,
    IntLiteral,
    FloatLiteral,
    LambdaForm,
    LetForm,
    MatchArm,
    MatchForm,
    ModuleForm,
    Node,
    Param,
    RaiseForm,
    SetForm,
    StringLiteral,
    Symbol,
    TypeForm,
)
from rigel.common import ParseError, Span
from rigel.lexer import Token, TokenKind, tokenize


# Type alias for the intermediate s-expression representation
SExpr = Node | list["SExpr"]


def parse(source: str, filename: str = "<stdin>") -> list[Node]:
    """Parse Rigel source text into a list of top-level AST nodes.

    Calls tokenize() internally.
    Raises ParseError on malformed input.
    """
    tokens = tokenize(source, filename)
    return parse_tokens(tokens)


def parse_tokens(tokens: list[Token]) -> list[Node]:
    """Parse a token list into AST nodes.

    Useful for testing the parser independently of the lexer.
    """
    sexprs = _read_sexprs(tokens)
    return [_recognize(s) for s in sexprs]


# --- Pass 1: Token stream → S-expression structure ---

def _read_sexprs(tokens: list[Token]) -> list[SExpr]:
    """Read all top-level s-expressions from the token stream."""
    pos = 0
    results: list[SExpr] = []

    def read_one() -> SExpr:
        nonlocal pos
        if pos >= len(tokens):
            raise ParseError(
                "unexpected end of input",
                tokens[-1].span if tokens else Span("<stdin>", 1, 1, 0, 0),
            )
        tok = tokens[pos]

        if tok.kind == TokenKind.LPAREN:
            return read_list(TokenKind.LPAREN, TokenKind.RPAREN)
        elif tok.kind == TokenKind.RPAREN:
            raise ParseError("unexpected ')'", tok.span)
        elif tok.kind == TokenKind.LBRACKET:
            raise ParseError("unexpected '['", tok.span)
        elif tok.kind == TokenKind.RBRACKET:
            raise ParseError("unexpected ']'", tok.span)
        else:
            pos += 1
            return _atom(tok)

    def read_list(open_kind: TokenKind, close_kind: TokenKind) -> list[SExpr]:
        nonlocal pos
        open_tok = tokens[pos]
        pos += 1  # skip opening paren
        items: list[SExpr] = []
        while pos < len(tokens) and tokens[pos].kind != close_kind:
            items.append(read_one())
        if pos >= len(tokens):
            raise ParseError(
                f"unmatched '{open_kind.value}'",
                open_tok.span,
            )
        pos += 1  # skip closing paren
        return items

    while pos < len(tokens):
        if tokens[pos].kind == TokenKind.EOF:
            break
        results.append(read_one())

    return results


def _atom(tok: Token) -> Node:
    """Convert a single token into an AST leaf node."""
    if tok.kind == TokenKind.INT:
        value, suffix = _parse_numeric_suffix(tok.text)
        return IntLiteral(value=int(value), type_suffix=suffix, span=tok.span)
    elif tok.kind == TokenKind.FLOAT:
        value, suffix = _parse_numeric_suffix(tok.text)
        return FloatLiteral(value=float(value), type_suffix=suffix, span=tok.span)
    elif tok.kind == TokenKind.STRING:
        # Strip quotes and unescape
        inner = tok.text[1:-1]
        unescaped = (
            inner.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )
        return StringLiteral(value=unescaped, span=tok.span)
    elif tok.kind == TokenKind.BOOL:
        return BoolLiteral(value=(tok.text == "true"), span=tok.span)
    elif tok.kind in (TokenKind.SYMBOL, TokenKind.KEYWORD):
        return Symbol(name=tok.text, span=tok.span)
    else:
        raise ParseError(f"unexpected token: {tok.kind.value}", tok.span)


def _parse_numeric_suffix(text: str) -> tuple[str, str | None]:
    """Split '42:int8' into ('42', 'int8') or '42' into ('42', None)."""
    if ":" in text:
        idx = text.index(":")
        return text[:idx], text[idx + 1:]
    return text, None


# --- Pass 2: S-expression → typed AST nodes ---

# Special form dispatch table
_FORM_DISPATCH: dict[str, "_FormParser"] = {}

# Type alias for form parser functions
type _FormParser = type[object]  # placeholder, actual type below


def _recognize(sexpr: SExpr) -> Node:
    """Recognize a special form or call from an s-expression."""
    if not isinstance(sexpr, list):
        return sexpr  # already an AST leaf node

    if not sexpr:
        raise ParseError("empty expression ()", Span("<unknown>", 1, 1, 0, 0))

    head = sexpr[0]
    if isinstance(head, Symbol) and head.name in _FORM_PARSERS:
        return _FORM_PARSERS[head.name](sexpr)

    # Default: call expression
    return _parse_call(sexpr)


def _span_of_sexpr(sexpr: SExpr) -> Span:
    """Extract or compute the span of an s-expression."""
    if isinstance(sexpr, list):
        if not sexpr:
            return Span("<unknown>", 1, 1, 0, 0)
        first = _span_of_sexpr(sexpr[0])
        last = _span_of_sexpr(sexpr[-1])
        return first.to(last)
    return sexpr.span


def _expect_symbol(sexpr: SExpr, context: str) -> Symbol:
    """Assert that sexpr is a Symbol."""
    node = _recognize(sexpr) if isinstance(sexpr, list) else sexpr
    if not isinstance(node, Symbol):
        raise ParseError(f"expected symbol in {context}, got {type(node).__name__}", _span_of_sexpr(sexpr))
    return node


# --- Individual form parsers ---

def _parse_let(sexpr: list[SExpr]) -> LetForm:
    """(let name value) or (let name :type ann value) or (let name :mut value)"""
    if len(sexpr) < 3:
        raise ParseError("'let' requires at least a name and value", _span_of_sexpr(sexpr))

    name = _expect_symbol(sexpr[1], "let")
    rest = sexpr[2:]

    type_ann: Node | None = None
    mutable = False

    # Consume keyword modifiers before the value
    while len(rest) >= 2 and isinstance(rest[0], Symbol):
        kw = rest[0].name
        if kw == ":type":
            if len(rest) < 3:
                raise ParseError("'let' with :type requires type and value", _span_of_sexpr(sexpr))
            type_ann = _recognize(rest[1])
            rest = rest[2:]
        elif kw == ":mut":
            mutable = True
            rest = rest[1:]
        else:
            break

    if len(rest) != 1:
        raise ParseError(f"'let' expects (let name [:mut] [:type T] value), got {len(sexpr)} elements",
                         _span_of_sexpr(sexpr))
    value = _recognize(rest[0])

    return LetForm(name=name, value=value, type_ann=type_ann, mutable=mutable, span=_span_of_sexpr(sexpr))


def _parse_set(sexpr: list[SExpr]) -> SetForm:
    """(set name value)"""
    if len(sexpr) != 3:
        raise ParseError(f"'set' expects (set name value), got {len(sexpr)} elements", _span_of_sexpr(sexpr))
    name = _expect_symbol(sexpr[1], "set")
    value = _recognize(sexpr[2])
    return SetForm(name=name, value=value, span=_span_of_sexpr(sexpr))


def _parse_lambda(sexpr: list[SExpr]) -> LambdaForm:
    """(lambda (:args ...) (:capture ...) (:returns type) (:with effects) body...)"""
    span = _span_of_sexpr(sexpr)
    rest = sexpr[1:]  # skip 'lambda'

    params: list[Param] = []
    captures: list[Capture] = []
    return_type: Node | None = None
    effects: list[Symbol] = []
    body_start = 0

    i = 0
    while i < len(rest):
        item = rest[i]
        if isinstance(item, list) and item and isinstance(item[0], Symbol):
            keyword = item[0].name
            if keyword == ":args":
                params = _parse_params(item[1:], span)
                i += 1
                continue
            elif keyword == ":capture":
                captures = _parse_captures(item[1:], span)
                i += 1
                continue
            elif keyword == ":returns":
                if len(item) != 2:
                    raise ParseError(":returns expects exactly one type", span)
                return_type = _recognize(item[1])
                i += 1
                continue
            elif keyword == ":with":
                # (:with (io fail)) → item[1] is the list of effect names
                if len(item) == 2 and isinstance(item[1], list):
                    effects = [_expect_symbol(e, ":with") for e in item[1]]
                else:
                    effects = [_expect_symbol(e, ":with") for e in item[1:]]
                i += 1
                continue
        # Not a keyword section — this and everything after is body
        body_start = i
        break
    else:
        body_start = len(rest)

    body_sexprs = rest[body_start:]
    if not body_sexprs:
        raise ParseError("lambda requires at least one body expression", span)
    body = [_recognize(b) for b in body_sexprs]

    return LambdaForm(
        params=params, captures=captures, return_type=return_type,
        effects=effects, body=body, span=span,
    )


def _parse_params(items: list[SExpr], parent_span: Span) -> list[Param]:
    """Parse parameter list: each item is (name type) or (name type default)."""
    params: list[Param] = []
    for item in items:
        if not isinstance(item, list):
            raise ParseError("parameter must be a list (name type)", parent_span)
        if len(item) < 2:
            raise ParseError("parameter requires name and type", _span_of_sexpr(item))
        name = _expect_symbol(item[0], "parameter")
        type_ann = _recognize(item[1])
        default = _recognize(item[2]) if len(item) > 2 else None
        params.append(Param(name=name, type_ann=type_ann, default=default, span=_span_of_sexpr(item)))
    return params


def _parse_captures(items: list[SExpr], parent_span: Span) -> list[Capture]:
    """Parse capture list: each item is (name) or (name :mut)."""
    captures: list[Capture] = []
    for item in items:
        if not isinstance(item, list):
            raise ParseError("capture must be a list", parent_span)
        if not item:
            raise ParseError("empty capture", parent_span)
        name = _expect_symbol(item[0], "capture")
        mut = any(isinstance(e, Symbol) and e.name == ":mut" for e in item[1:])
        captures.append(Capture(name=name, mut=mut, span=_span_of_sexpr(item)))
    return captures


def _parse_type(sexpr: list[SExpr]) -> TypeForm:
    """(type (:fields ...) (:invariant expr) (:constructor ...) (:viewer ...) (:release ...))"""
    span = _span_of_sexpr(sexpr)
    rest = sexpr[1:]

    fields: list[Field] = []
    invariant: Node | None = None
    constructor: Node | None = None
    viewer: Node | None = None
    release: Node | None = None

    for item in rest:
        if not isinstance(item, list) or not item:
            raise ParseError("type expects keyword sections", span)
        head = item[0]
        if not isinstance(head, Symbol):
            raise ParseError("type section must start with a keyword", span)

        if head.name == ":fields":
            fields = _parse_fields(item[1:], span)
        elif head.name == ":invariant":
            if len(item) != 2:
                raise ParseError(":invariant expects one expression", span)
            invariant = _recognize(item[1])
        elif head.name == ":constructor":
            if len(item) != 2:
                raise ParseError(":constructor expects one expression", span)
            constructor = _recognize(item[1])
        elif head.name == ":viewer":
            if len(item) != 2:
                raise ParseError(":viewer expects one expression", span)
            viewer = _recognize(item[1])
        elif head.name == ":release":
            if len(item) != 2:
                raise ParseError(":release expects one expression", span)
            release = _recognize(item[1])
        else:
            raise ParseError(f"unknown type section: {head.name}", span)

    return TypeForm(
        fields=fields, invariant=invariant, constructor=constructor,
        viewer=viewer, release=release, span=span,
    )


def _parse_fields(items: list[SExpr], parent_span: Span) -> list[Field]:
    """Parse field list: each item is (name type) or (name type :mut)."""
    fields: list[Field] = []
    for item in items:
        if not isinstance(item, list):
            raise ParseError("field must be a list (name type)", parent_span)
        if len(item) < 2:
            raise ParseError("field requires name and type", _span_of_sexpr(item))
        name = _expect_symbol(item[0], "field")
        type_ann = _recognize(item[1])
        mut = any(isinstance(e, Symbol) and e.name == ":mut" for e in item[2:])
        fields.append(Field(name=name, type_ann=type_ann, mut=mut, span=_span_of_sexpr(item)))
    return fields


def _parse_if(sexpr: list[SExpr]) -> IfForm:
    """(if cond then else?)"""
    if len(sexpr) < 3 or len(sexpr) > 4:
        raise ParseError("'if' expects 2 or 3 arguments", _span_of_sexpr(sexpr))
    condition = _recognize(sexpr[1])
    then_branch = _recognize(sexpr[2])
    else_branch = _recognize(sexpr[3]) if len(sexpr) == 4 else None
    return IfForm(condition=condition, then_branch=then_branch, else_branch=else_branch, span=_span_of_sexpr(sexpr))


def _parse_cond(sexpr: list[SExpr]) -> CondForm:
    """(cond (test body)... (:else body)?)"""
    span = _span_of_sexpr(sexpr)
    rest = sexpr[1:]
    if not rest:
        raise ParseError("'cond' requires at least one clause", span)

    clauses: list[tuple[Node, Node]] = []
    else_clause: Node | None = None

    for item in rest:
        if not isinstance(item, list) or len(item) != 2:
            raise ParseError("cond clause must be (test body)", span)
        test_expr = item[0]
        body_expr = item[1]
        if isinstance(test_expr, Symbol) and test_expr.name == ":else":
            else_clause = _recognize(body_expr)
        else:
            clauses.append((_recognize(test_expr), _recognize(body_expr)))

    return CondForm(clauses=clauses, else_clause=else_clause, span=span)


def _parse_match(sexpr: list[SExpr]) -> MatchForm:
    """(match target (pattern body)...)"""
    span = _span_of_sexpr(sexpr)
    if len(sexpr) < 3:
        raise ParseError("'match' requires target and at least one arm", span)

    target = _recognize(sexpr[1])
    arms: list[MatchArm] = []

    for item in sexpr[2:]:
        if not isinstance(item, list) or len(item) < 2:
            raise ParseError("match arm must be (pattern body)", span)
        pattern = _recognize(item[0])
        # Optional guard: (pattern :when guard body)
        if len(item) >= 4 and isinstance(item[1], Symbol) and item[1].name == ":when":
            guard = _recognize(item[2])
            body = _recognize(item[3])
        else:
            guard = None
            body = _recognize(item[1])
        arms.append(MatchArm(pattern=pattern, guard=guard, body=body, span=_span_of_sexpr(item)))

    return MatchForm(target=target, arms=arms, span=span)


def _parse_do(sexpr: list[SExpr]) -> DoForm:
    """(do expr...)"""
    span = _span_of_sexpr(sexpr)
    if len(sexpr) < 2:
        raise ParseError("'do' requires at least one expression", span)
    body = [_recognize(e) for e in sexpr[1:]]
    return DoForm(body=body, span=span)


def _parse_module(sexpr: list[SExpr]) -> ModuleForm:
    """(module name (:export ...) body...)"""
    span = _span_of_sexpr(sexpr)
    if len(sexpr) < 2:
        raise ParseError("'module' requires a name", span)

    name = _expect_symbol(sexpr[1], "module")
    rest = sexpr[2:]
    exports: list[Symbol] = []
    body_start = 0

    for i, item in enumerate(rest):
        if isinstance(item, list) and item and isinstance(item[0], Symbol) and item[0].name == ":export":
            exports = [_expect_symbol(e, ":export") for e in item[1:]]
            body_start = i + 1
            continue
        body_start = i
        break
    else:
        body_start = len(rest)

    body = [_recognize(e) for e in rest[body_start:]]
    return ModuleForm(name=name, exports=exports, body=body, span=span)


def _parse_import(sexpr: list[SExpr]) -> ImportForm:
    """(import module) or (import module :only (names...)) or (import module :as alias)"""
    span = _span_of_sexpr(sexpr)
    if len(sexpr) < 2:
        raise ParseError("'import' requires a module name", span)

    module = _expect_symbol(sexpr[1], "import")
    names: list[Symbol] | None = None
    alias: Symbol | None = None

    rest = sexpr[2:]
    i = 0
    while i < len(rest):
        item = rest[i]
        if isinstance(item, Symbol) and item.name == ":only":
            i += 1
            if i >= len(rest) or not isinstance(rest[i], list):
                raise ParseError(":only requires a list of names", span)
            names = [_expect_symbol(n, ":only") for n in rest[i]]
            i += 1
        elif isinstance(item, Symbol) and item.name == ":as":
            i += 1
            if i >= len(rest):
                raise ParseError(":as requires an alias", span)
            alias = _expect_symbol(rest[i], ":as")
            i += 1
        else:
            raise ParseError(f"unexpected in import: {type(item).__name__}", span)

    return ImportForm(module=module, names=names, alias=alias, span=span)


def _parse_handle(sexpr: list[SExpr]) -> HandleForm:
    """(handle body (effect-name (params...) handler-body)...)"""
    span = _span_of_sexpr(sexpr)
    if len(sexpr) < 3:
        raise ParseError("'handle' requires body and at least one handler", span)

    body = _recognize(sexpr[1])
    handlers: list[HandlerClause] = []

    for item in sexpr[2:]:
        if not isinstance(item, list) or len(item) < 3:
            raise ParseError("handler clause must be (effect (params...) body)", span)
        effect = _expect_symbol(item[0], "handler effect")

        if not isinstance(item[1], list):
            raise ParseError("handler params must be a list", span)
        # Handler params are just names (no types) — synthesize Param nodes
        handler_params: list[Param] = []
        for p in item[1]:
            sym = _expect_symbol(p, "handler param")
            handler_params.append(Param(
                name=sym,
                type_ann=Symbol(name="any", span=sym.span),
                default=None,
                span=sym.span,
            ))

        handler_body = _recognize(item[2])
        # Optional resume binding
        resume: Symbol | None = None
        if len(item) > 3:
            resume = _expect_symbol(item[3], "resume")

        handlers.append(HandlerClause(
            effect=effect, params=handler_params, body=handler_body,
            resume=resume, span=_span_of_sexpr(item),
        ))

    return HandleForm(body=body, handlers=handlers, span=span)


def _parse_raise(sexpr: list[SExpr]) -> RaiseForm:
    """(raise effect args...)"""
    span = _span_of_sexpr(sexpr)
    if len(sexpr) < 2:
        raise ParseError("'raise' requires an effect name", span)
    effect = _expect_symbol(sexpr[1], "raise")
    args = [_recognize(a) for a in sexpr[2:]]
    return RaiseForm(effect=effect, args=args, span=span)


def _parse_call(sexpr: list[SExpr]) -> CallForm:
    """(f x y z) — generic function call."""
    if not sexpr:
        raise ParseError("empty call expression", Span("<unknown>", 1, 1, 0, 0))
    func = _recognize(sexpr[0])
    args = [_recognize(a) for a in sexpr[1:]]
    return CallForm(func=func, args=args, span=_span_of_sexpr(sexpr))


# Dispatch table
_FORM_PARSERS: dict[str, type[object] | object] = {
    "let": _parse_let,
    "set": _parse_set,
    "lambda": _parse_lambda,
    "type": _parse_type,
    "if": _parse_if,
    "cond": _parse_cond,
    "match": _parse_match,
    "do": _parse_do,
    "module": _parse_module,
    "import": _parse_import,
    "handle": _parse_handle,
    "raise": _parse_raise,
}
