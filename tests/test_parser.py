"""Tests for the Rigel parser."""

from __future__ import annotations

import pytest

from rigel.ast import (
    BoolLiteral, CallForm, Capture, CondForm, DoForm, Field,
    FloatLiteral, HandleForm, IfForm, ImportForm, IntLiteral,
    LambdaForm, LetForm, MatchArm, MatchForm, ModuleForm,
    Param, RaiseForm, SetForm, StringLiteral, Symbol, TypeForm,
)
from rigel.common import ParseError
from rigel.parser import parse


def parse_one(source: str):
    nodes = parse(source)
    assert len(nodes) == 1, f"expected 1 node, got {len(nodes)}"
    return nodes[0]


class TestLet:
    """let form parsing."""

    def test_let_simple(self):
        node = parse_one("(let x 42)")
        assert isinstance(node, LetForm)
        assert node.name.name == "x"
        assert isinstance(node.value, IntLiteral)
        assert node.value.value == 42
        assert node.type_ann is None

    def test_let_with_type(self):
        node = parse_one("(let x :type int64 42)")
        assert isinstance(node, LetForm)
        assert node.name.name == "x"
        assert isinstance(node.type_ann, Symbol)
        assert node.type_ann.name == "int64"
        assert isinstance(node.value, IntLiteral)

    def test_let_with_lambda(self):
        node = parse_one("(let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b)))")
        assert isinstance(node, LetForm)
        assert node.name.name == "add"
        assert isinstance(node.value, LambdaForm)

    def test_let_wrong_arity(self):
        with pytest.raises(ParseError):
            parse_one("(let x)")


class TestSet:
    """set form parsing."""

    def test_set_simple(self):
        node = parse_one("(set x 43)")
        assert isinstance(node, SetForm)
        assert node.name.name == "x"
        assert isinstance(node.value, IntLiteral)
        assert node.value.value == 43

    def test_set_wrong_arity(self):
        with pytest.raises(ParseError):
            parse_one("(set x)")


class TestLambda:
    """lambda form parsing."""

    def test_lambda_minimal(self):
        node = parse_one("(lambda (:args (x int64)) x)")
        assert isinstance(node, LambdaForm)
        assert len(node.params) == 1
        assert node.params[0].name.name == "x"
        assert isinstance(node.params[0].type_ann, Symbol)
        assert node.params[0].type_ann.name == "int64"
        assert len(node.body) == 1

    def test_lambda_full(self):
        src = "(lambda (:args (x int64) (y int64)) (:capture (z)) (:returns int64) (:with (io)) (+ x y))"
        node = parse_one(src)
        assert isinstance(node, LambdaForm)
        assert len(node.params) == 2
        assert len(node.captures) == 1
        assert node.captures[0].name.name == "z"
        assert isinstance(node.return_type, Symbol)
        assert node.return_type.name == "int64"
        assert len(node.effects) == 1
        assert node.effects[0].name == "io"
        assert len(node.body) == 1

    def test_lambda_parameter_default(self):
        node = parse_one("(lambda (:args (x int64 42)) x)")
        assert isinstance(node, LambdaForm)
        assert len(node.params) == 1
        assert node.params[0].default is not None
        assert isinstance(node.params[0].default, IntLiteral)
        assert node.params[0].default.value == 42

    def test_lambda_mutable_capture(self):
        node = parse_one("(lambda (:args (x int64)) (:capture (z :mut)) x)")
        assert isinstance(node, LambdaForm)
        assert len(node.captures) == 1
        assert node.captures[0].name.name == "z"
        assert node.captures[0].mut is True

    def test_lambda_no_body(self):
        with pytest.raises(ParseError, match="body"):
            parse_one("(lambda (:args (x int64)))")


class TestType:
    """type form parsing."""

    def test_type_minimal(self):
        node = parse_one("(type (:fields (x int64)))")
        assert isinstance(node, TypeForm)
        assert len(node.fields) == 1
        assert node.fields[0].name.name == "x"

    def test_type_with_invariant(self):
        node = parse_one("(type (:fields (value int64)) (:invariant (>= value 0)))")
        assert isinstance(node, TypeForm)
        assert node.invariant is not None
        assert isinstance(node.invariant, CallForm)

    def test_type_with_constructor(self):
        node = parse_one("(type (:fields (x int64)) (:constructor (lambda (:args (v int64)) v)))")
        assert isinstance(node, TypeForm)
        assert node.constructor is not None
        assert isinstance(node.constructor, LambdaForm)

    def test_type_with_viewer(self):
        node = parse_one("(type (:fields (x int64)) (:viewer (lambda (:args (self self-type)) (.x self))))")
        assert isinstance(node, TypeForm)
        assert node.viewer is not None
        assert isinstance(node.viewer, LambdaForm)

    def test_type_with_release(self):
        node = parse_one("(type (:fields (handle int64)) (:release (lambda (:args (self self-type)) (close self))))")
        assert isinstance(node, TypeForm)
        assert node.release is not None
        assert isinstance(node.release, LambdaForm)

    def test_type_mutable_field(self):
        node = parse_one("(type (:fields (x int64 :mut) (y int64)))")
        assert isinstance(node, TypeForm)
        assert len(node.fields) == 2
        assert node.fields[0].mut is True
        assert node.fields[1].mut is False


class TestIf:
    """if form parsing."""

    def test_if_two_arm(self):
        node = parse_one("(if true 1 2)")
        assert isinstance(node, IfForm)
        assert isinstance(node.condition, BoolLiteral)
        assert node.condition.value is True
        assert isinstance(node.then_branch, IntLiteral)
        assert node.then_branch.value == 1
        assert isinstance(node.else_branch, IntLiteral)
        assert node.else_branch.value == 2

    def test_if_one_arm(self):
        node = parse_one("(if true 1)")
        assert isinstance(node, IfForm)
        assert node.else_branch is None

    def test_if_wrong_arity(self):
        with pytest.raises(ParseError):
            parse_one("(if true)")


class TestCond:
    """cond form parsing."""

    def test_cond(self):
        node = parse_one('(cond ((> x 0) "positive") ((< x 0) "negative") (:else "zero"))')
        assert isinstance(node, CondForm)
        assert len(node.clauses) == 2
        assert isinstance(node.else_clause, StringLiteral)
        assert node.else_clause.value == "zero"


class TestMatch:
    """match form parsing."""

    def test_match(self):
        node = parse_one('(match x (0 "zero") (1 "one") (_ "other"))')
        assert isinstance(node, MatchForm)
        assert isinstance(node.target, Symbol)
        assert node.target.name == "x"
        assert len(node.arms) == 3
        assert isinstance(node.arms[0].pattern, IntLiteral)
        assert isinstance(node.arms[2].pattern, Symbol)
        assert node.arms[2].pattern.name == "_"

    def test_match_with_guard(self):
        node = parse_one('(match x (n :when (> n 0) "positive") (_ "other"))')
        assert isinstance(node, MatchForm)
        assert len(node.arms) == 2
        assert node.arms[0].guard is not None
        assert isinstance(node.arms[0].guard, CallForm)
        assert isinstance(node.arms[0].body, StringLiteral)
        assert node.arms[0].body.value == "positive"
        assert node.arms[1].guard is None


class TestDo:
    """do form parsing."""

    def test_do(self):
        node = parse_one("(do 1 2 3)")
        assert isinstance(node, DoForm)
        assert len(node.body) == 3

    def test_do_with_let(self):
        node = parse_one("(do (let x 1) (let y 2) (+ x y))")
        assert isinstance(node, DoForm)
        assert len(node.body) == 3
        assert isinstance(node.body[0], LetForm)
        assert isinstance(node.body[1], LetForm)
        assert isinstance(node.body[2], CallForm)


class TestModule:
    """module form parsing."""

    def test_module(self):
        src = "(module math (:export add sub) (let add (lambda (:args (a int64)) a)))"
        node = parse_one(src)
        assert isinstance(node, ModuleForm)
        assert node.name.name == "math"
        assert len(node.exports) == 2
        assert node.exports[0].name == "add"
        assert len(node.body) == 1


class TestImport:
    """import form parsing."""

    def test_import_basic(self):
        node = parse_one("(import math)")
        assert isinstance(node, ImportForm)
        assert node.module.name == "math"
        assert node.names is None
        assert node.alias is None

    def test_import_only(self):
        node = parse_one("(import math :only (add))")
        assert isinstance(node, ImportForm)
        assert node.names is not None
        assert len(node.names) == 1
        assert node.names[0].name == "add"

    def test_import_as(self):
        node = parse_one("(import math :as m)")
        assert isinstance(node, ImportForm)
        assert node.alias is not None
        assert node.alias.name == "m"


class TestHandle:
    """handle/raise form parsing."""

    def test_handle(self):
        node = parse_one("(handle (raise fail \"oops\") (fail (msg) (println msg)))")
        assert isinstance(node, HandleForm)
        assert isinstance(node.body, RaiseForm)
        assert len(node.handlers) == 1
        assert node.handlers[0].effect.name == "fail"

    def test_raise(self):
        node = parse_one('(raise fail "error")')
        assert isinstance(node, RaiseForm)
        assert node.effect.name == "fail"
        assert len(node.args) == 1


class TestCall:
    """Call expression parsing."""

    def test_call_no_args(self):
        node = parse_one("(f)")
        assert isinstance(node, CallForm)
        assert isinstance(node.func, Symbol)
        assert node.func.name == "f"
        assert len(node.args) == 0

    def test_call_one_arg(self):
        node = parse_one("(f x)")
        assert isinstance(node, CallForm)
        assert len(node.args) == 1

    def test_call_multiple_args(self):
        node = parse_one("(f x y z)")
        assert isinstance(node, CallForm)
        assert len(node.args) == 3

    def test_call_computed_function(self):
        node = parse_one("((get-fn) x)")
        assert isinstance(node, CallForm)
        assert isinstance(node.func, CallForm)

    def test_call_nested(self):
        node = parse_one("(f (g x) (h y))")
        assert isinstance(node, CallForm)
        assert isinstance(node.args[0], CallForm)
        assert isinstance(node.args[1], CallForm)

    def test_arithmetic(self):
        node = parse_one("(+ 1 2)")
        assert isinstance(node, CallForm)
        assert isinstance(node.func, Symbol)
        assert node.func.name == "+"
        assert len(node.args) == 2


class TestNesting:
    """Nested and composed expressions."""

    def test_let_binding_lambda(self):
        src = "(let inc (lambda (:args (x int64)) (:returns int64) (+ x 1)))"
        node = parse_one(src)
        assert isinstance(node, LetForm)
        assert isinstance(node.value, LambdaForm)
        assert len(node.value.params) == 1
        assert isinstance(node.value.body[0], CallForm)

    def test_nested_if(self):
        node = parse_one("(if true (if false 1 2) 3)")
        assert isinstance(node, IfForm)
        assert isinstance(node.then_branch, IfForm)

    def test_multiple_top_level(self):
        nodes = parse("(let x 1) (let y 2)")
        assert len(nodes) == 2
        assert all(isinstance(n, LetForm) for n in nodes)


class TestErrors:
    """Parser error handling."""

    def test_unmatched_open_paren(self):
        with pytest.raises(ParseError, match="unmatched"):
            parse("(let x")

    def test_unmatched_close_paren(self):
        with pytest.raises(ParseError):
            parse(")")

    def test_empty_input(self):
        nodes = parse("")
        assert nodes == []

    def test_let_missing_value(self):
        with pytest.raises(ParseError):
            parse_one("(let x)")
