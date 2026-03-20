"""Roundtrip tests: parse → pretty-print → re-parse gives structurally equal AST.

Validates that the parser preserves enough structure to reconstruct equivalent source,
and that re-parsing produces the same AST (modulo spans).
"""

from __future__ import annotations

from rigel.ast import (
    BoolLiteral, CallForm, Capture, CondForm, DoForm, Field,
    FloatLiteral, HandleForm, HandlerClause, IfForm, ImportForm,
    IntLiteral, LambdaForm, LetForm, MatchArm, MatchForm,
    ModuleForm, Node, Param, RaiseForm, SetForm, StringLiteral,
    Symbol, TypeForm,
)
from rigel.parser import parse


# --- Minimal pretty-printer (for roundtrip testing only) ---

def pp(node: Node) -> str:
    """Pretty-print an AST node back to Rigel source text."""
    match node:
        case IntLiteral(value=v, type_suffix=s):
            return f"{v}:{s}" if s else str(v)
        case FloatLiteral(value=v, type_suffix=s):
            text = f"{v:g}"
            if "." not in text:
                text += ".0"
            return f"{text}:{s}" if s else text
        case StringLiteral(value=v):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
            return f'"{escaped}"'
        case BoolLiteral(value=v):
            return "true" if v else "false"
        case Symbol(name=n):
            return n
        case LetForm(name=name, value=val, type_ann=ann):
            if ann:
                return f"(let {pp(name)} :type {pp(ann)} {pp(val)})"
            return f"(let {pp(name)} {pp(val)})"
        case SetForm(name=name, value=val):
            return f"(set {pp(name)} {pp(val)})"
        case LambdaForm(params=params, captures=caps, return_type=ret, effects=effs, body=body):
            parts = ["lambda"]
            if params:
                args_str = " ".join(f"({pp(p.name)} {pp(p.type_ann)}{' ' + pp(p.default) if p.default else ''})"
                                    for p in params)
                parts.append(f"(:args {args_str})")
            if caps:
                caps_str = " ".join(f"({pp(c.name)}{' :mut' if c.mut else ''})" for c in caps)
                parts.append(f"(:capture {caps_str})")
            if ret:
                parts.append(f"(:returns {pp(ret)})")
            if effs:
                effs_str = " ".join(pp(e) for e in effs)
                parts.append(f"(:with ({effs_str}))")
            parts.extend(pp(b) for b in body)
            return f"({' '.join(parts)})"
        case TypeForm(fields=fields, invariant=inv, constructor=con, viewer=vw, release=rel):
            parts = ["type"]
            if fields:
                fields_str = " ".join(f"({pp(f.name)} {pp(f.type_ann)}{' :mut' if f.mut else ''})" for f in fields)
                parts.append(f"(:fields {fields_str})")
            if inv:
                parts.append(f"(:invariant {pp(inv)})")
            if con:
                parts.append(f"(:constructor {pp(con)})")
            if vw:
                parts.append(f"(:viewer {pp(vw)})")
            if rel:
                parts.append(f"(:release {pp(rel)})")
            return f"({' '.join(parts)})"
        case IfForm(condition=cond, then_branch=then_, else_branch=else_):
            if else_:
                return f"(if {pp(cond)} {pp(then_)} {pp(else_)})"
            return f"(if {pp(cond)} {pp(then_)})"
        case CondForm(clauses=clauses, else_clause=else_):
            parts = ["cond"]
            for test, body in clauses:
                parts.append(f"({pp(test)} {pp(body)})")
            if else_:
                parts.append(f"(:else {pp(else_)})")
            return f"({' '.join(parts)})"
        case MatchForm(target=tgt, arms=arms):
            parts = ["match", pp(tgt)]
            for arm in arms:
                if arm.guard:
                    parts.append(f"({pp(arm.pattern)} :when {pp(arm.guard)} {pp(arm.body)})")
                else:
                    parts.append(f"({pp(arm.pattern)} {pp(arm.body)})")
            return f"({' '.join(parts)})"
        case CallForm(func=func, args=args):
            return f"({pp(func)} {' '.join(pp(a) for a in args)})" if args else f"({pp(func)})"
        case DoForm(body=body):
            return f"(do {' '.join(pp(b) for b in body)})"
        case ModuleForm(name=name, exports=exports, body=body):
            parts = ["module", pp(name)]
            if exports:
                parts.append(f"(:export {' '.join(pp(e) for e in exports)})")
            parts.extend(pp(b) for b in body)
            return f"({' '.join(parts)})"
        case ImportForm(module=mod, names=names, alias=alias):
            parts = ["import", pp(mod)]
            if names is not None:
                parts.append(f":only ({' '.join(pp(n) for n in names)})")
            if alias:
                parts.append(f":as {pp(alias)}")
            return f"({' '.join(parts)})"
        case HandleForm(body=body, handlers=handlers):
            parts = ["handle", pp(body)]
            for h in handlers:
                params_str = " ".join(pp(p.name) for p in h.params)
                parts.append(f"({pp(h.effect)} ({params_str}) {pp(h.body)})")
            return f"({' '.join(parts)})"
        case RaiseForm(effect=eff, args=args):
            parts = ["raise", pp(eff)]
            parts.extend(pp(a) for a in args)
            return f"({' '.join(parts)})"
        case _:
            raise ValueError(f"unhandled node type: {type(node).__name__}")


def ast_equal(a: Node, b: Node) -> bool:
    """Compare two AST nodes for structural equality, ignoring spans."""
    match (a, b):
        case (IntLiteral() as x, IntLiteral() as y):
            return x.value == y.value and x.type_suffix == y.type_suffix
        case (FloatLiteral() as x, FloatLiteral() as y):
            return x.value == y.value and x.type_suffix == y.type_suffix
        case (StringLiteral() as x, StringLiteral() as y):
            return x.value == y.value
        case (BoolLiteral() as x, BoolLiteral() as y):
            return x.value == y.value
        case (Symbol() as x, Symbol() as y):
            return x.name == y.name
        case (LetForm() as x, LetForm() as y):
            return (ast_equal(x.name, y.name) and ast_equal(x.value, y.value)
                    and _opt_eq(x.type_ann, y.type_ann))
        case (SetForm() as x, SetForm() as y):
            return ast_equal(x.name, y.name) and ast_equal(x.value, y.value)
        case (LambdaForm() as x, LambdaForm() as y):
            return (_list_eq_params(x.params, y.params)
                    and _list_eq_captures(x.captures, y.captures)
                    and _opt_eq(x.return_type, y.return_type)
                    and _list_eq(x.effects, y.effects)
                    and _list_eq(x.body, y.body))
        case (TypeForm() as x, TypeForm() as y):
            return (_list_eq_fields(x.fields, y.fields)
                    and _opt_eq(x.invariant, y.invariant)
                    and _opt_eq(x.constructor, y.constructor)
                    and _opt_eq(x.viewer, y.viewer)
                    and _opt_eq(x.release, y.release))
        case (IfForm() as x, IfForm() as y):
            return (ast_equal(x.condition, y.condition)
                    and ast_equal(x.then_branch, y.then_branch)
                    and _opt_eq(x.else_branch, y.else_branch))
        case (CondForm() as x, CondForm() as y):
            return (_list_eq_tuples(x.clauses, y.clauses)
                    and _opt_eq(x.else_clause, y.else_clause))
        case (MatchForm() as x, MatchForm() as y):
            return (ast_equal(x.target, y.target)
                    and len(x.arms) == len(y.arms)
                    and all(_arm_eq(a, b) for a, b in zip(x.arms, y.arms)))
        case (CallForm() as x, CallForm() as y):
            return ast_equal(x.func, y.func) and _list_eq(x.args, y.args)
        case (DoForm() as x, DoForm() as y):
            return _list_eq(x.body, y.body)
        case (ModuleForm() as x, ModuleForm() as y):
            return (ast_equal(x.name, y.name)
                    and _list_eq(x.exports, y.exports)
                    and _list_eq(x.body, y.body))
        case (ImportForm() as x, ImportForm() as y):
            return (ast_equal(x.module, y.module)
                    and _opt_list_eq(x.names, y.names)
                    and _opt_eq(x.alias, y.alias))
        case (HandleForm() as x, HandleForm() as y):
            return (ast_equal(x.body, y.body)
                    and len(x.handlers) == len(y.handlers)
                    and all(_handler_eq(a, b) for a, b in zip(x.handlers, y.handlers)))
        case (RaiseForm() as x, RaiseForm() as y):
            return ast_equal(x.effect, y.effect) and _list_eq(x.args, y.args)
        case _:
            return False


def _opt_eq(a: Node | None, b: Node | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return ast_equal(a, b)


def _list_eq(xs: list[Node], ys: list[Node]) -> bool:
    return len(xs) == len(ys) and all(ast_equal(x, y) for x, y in zip(xs, ys))


def _opt_list_eq(xs: list[Node] | None, ys: list[Node] | None) -> bool:
    if xs is None and ys is None:
        return True
    if xs is None or ys is None:
        return False
    return _list_eq(xs, ys)


def _list_eq_params(xs: list[Param], ys: list[Param]) -> bool:
    return (len(xs) == len(ys)
            and all(ast_equal(a.name, b.name) and ast_equal(a.type_ann, b.type_ann)
                    and _opt_eq(a.default, b.default)
                    for a, b in zip(xs, ys)))


def _list_eq_captures(xs: list[Capture], ys: list[Capture]) -> bool:
    return (len(xs) == len(ys)
            and all(ast_equal(a.name, b.name) and a.mut == b.mut for a, b in zip(xs, ys)))


def _list_eq_fields(xs: list[Field], ys: list[Field]) -> bool:
    return (len(xs) == len(ys)
            and all(ast_equal(a.name, b.name) and ast_equal(a.type_ann, b.type_ann)
                    and a.mut == b.mut for a, b in zip(xs, ys)))


def _list_eq_tuples(xs: list[tuple[Node, Node]], ys: list[tuple[Node, Node]]) -> bool:
    return (len(xs) == len(ys)
            and all(ast_equal(a[0], b[0]) and ast_equal(a[1], b[1]) for a, b in zip(xs, ys)))


def _arm_eq(a: MatchArm, b: MatchArm) -> bool:
    return (ast_equal(a.pattern, b.pattern) and _opt_eq(a.guard, b.guard)
            and ast_equal(a.body, b.body))


def _handler_eq(a: HandlerClause, b: HandlerClause) -> bool:
    return (ast_equal(a.effect, b.effect)
            and len(a.params) == len(b.params)
            and all(ast_equal(x.name, y.name) for x, y in zip(a.params, b.params))
            and ast_equal(a.body, b.body))


# --- Roundtrip test helper ---

def assert_roundtrip(source: str) -> None:
    """Parse source, pretty-print, re-parse, and assert structural equality."""
    ast1 = parse(source)
    printed = " ".join(pp(n) for n in ast1)
    ast2 = parse(printed)
    assert len(ast1) == len(ast2), f"node count mismatch: {len(ast1)} vs {len(ast2)}\nprinted: {printed}"
    for i, (a, b) in enumerate(zip(ast1, ast2)):
        assert ast_equal(a, b), (
            f"AST mismatch at index {i}:\n"
            f"  original source: {source}\n"
            f"  printed:         {printed}\n"
            f"  node1: {a}\n"
            f"  node2: {b}"
        )


# --- Tests ---

class TestRoundtripAtoms:
    """Atoms survive roundtrip."""

    def test_integer(self):
        assert_roundtrip("42")

    def test_negative_integer(self):
        assert_roundtrip("-7")

    def test_float(self):
        assert_roundtrip("3.14")

    def test_string(self):
        assert_roundtrip('"hello world"')

    def test_string_with_escapes(self):
        assert_roundtrip(r'"hello \"world\""')

    def test_bool(self):
        assert_roundtrip("true")
        assert_roundtrip("false")

    def test_symbol(self):
        assert_roundtrip("x")


class TestRoundtripForms:
    """Core forms survive roundtrip."""

    def test_let(self):
        assert_roundtrip("(let x 42)")

    def test_let_with_type(self):
        assert_roundtrip("(let x :type int64 42)")

    def test_set(self):
        assert_roundtrip("(set x 43)")

    def test_lambda_minimal(self):
        assert_roundtrip("(lambda (:args (x int64)) x)")

    def test_lambda_full(self):
        assert_roundtrip(
            "(lambda (:args (x int64) (y int64)) (:capture (z)) (:returns int64) (:with (io)) (+ x y))"
        )

    def test_lambda_mutable_capture(self):
        assert_roundtrip("(lambda (:args (x int64)) (:capture (z :mut)) x)")

    def test_lambda_default_param(self):
        assert_roundtrip("(lambda (:args (x int64 42)) x)")

    def test_type_minimal(self):
        assert_roundtrip("(type (:fields (x int64)))")

    def test_type_mutable_field(self):
        assert_roundtrip("(type (:fields (x int64 :mut) (y int64)))")

    def test_type_with_invariant(self):
        assert_roundtrip("(type (:fields (value int64)) (:invariant (>= value 0)))")

    def test_if_two_arm(self):
        assert_roundtrip("(if true 1 2)")

    def test_if_one_arm(self):
        assert_roundtrip("(if true 1)")

    def test_cond(self):
        assert_roundtrip('(cond ((> x 0) "positive") ((< x 0) "negative") (:else "zero"))')

    def test_match(self):
        assert_roundtrip('(match x (0 "zero") (1 "one") (_ "other"))')

    def test_match_with_guard(self):
        assert_roundtrip('(match x (n :when (> n 0) "positive") (_ "other"))')

    def test_do(self):
        assert_roundtrip("(do (let x 1) (let y 2) (+ x y))")

    def test_call(self):
        assert_roundtrip("(f x y z)")

    def test_call_nested(self):
        assert_roundtrip("(f (g x) (h y))")

    def test_module(self):
        assert_roundtrip("(module math (:export add) (let add (lambda (:args (a int64)) a)))")

    def test_import_basic(self):
        assert_roundtrip("(import math)")

    def test_import_only(self):
        assert_roundtrip("(import math :only (add sub))")

    def test_import_as(self):
        assert_roundtrip("(import math :as m)")

    def test_handle(self):
        assert_roundtrip('(handle (raise fail "oops") (fail (msg) (println msg)))')

    def test_raise(self):
        assert_roundtrip('(raise fail "error")')


class TestRoundtripComposition:
    """Nested and composed expressions survive roundtrip."""

    def test_let_binding_lambda(self):
        assert_roundtrip("(let inc (lambda (:args (x int64)) (:returns int64) (+ x 1)))")

    def test_nested_if(self):
        assert_roundtrip("(if true (if false 1 2) 3)")

    def test_multiple_top_level(self):
        assert_roundtrip("(let x 1) (let y 2)")

    def test_deeply_nested(self):
        assert_roundtrip("(let result (do (let x (+ 1 2)) (let y (if true x 0)) (+ x y)))")
