"""Tests for Rigel semantic analysis (Plan 05).

Tests name resolution, type checking, and effect checking.
Each test parses source text → checks it → inspects the checked IR.
"""

from __future__ import annotations

import pytest

from rigel.ast import Node
from rigel.check import (
    Checker,
    TBoolLiteral,
    TCallForm,
    TDoForm,
    TFloatLiteral,
    THandleForm,
    TIfForm,
    TIntLiteral,
    TLambdaForm,
    TLetForm,
    TRaiseForm,
    TSetForm,
    TStringLiteral,
    TSymbol,
    TypedExpr,
    check,
)
from rigel.common import EffectError, NameError_, TypeError_
from rigel.parser import parse
from rigel.types import (
    BOOL, FLOAT32, FLOAT64, INT8, INT16, INT32, INT64, NEVER, STRING, UNIT,
    FnType, FloatType, IntType, Qualifier,
)


def check_one(source: str) -> TypedExpr:
    """Parse and check a single expression."""
    result = check(parse(source))
    assert len(result) == 1
    return result[0]


def check_all(source: str) -> list[TypedExpr]:
    """Parse and check multiple expressions."""
    return check(parse(source))


# --- §2 Literal type defaults ---

class TestLiterals:
    """Spec §2.1: literal defaults and type suffixes."""

    def test_int_literal_defaults_to_int64(self):
        # §2.1: "Unadorned 42 is int64"
        r = check_one("42")
        assert isinstance(r, TIntLiteral)
        assert r.ty == INT64
        assert r.value == 42

    def test_float_literal_defaults_to_float64(self):
        # §2.1: "Unadorned 3.14 is float64"
        r = check_one("3.14")
        assert isinstance(r, TFloatLiteral)
        assert r.ty == FLOAT64
        assert r.value == 3.14

    def test_int_literal_with_suffix(self):
        # §2.1: "42:int8" → int8
        r = check_one("42:int8")
        assert isinstance(r, TIntLiteral)
        assert r.ty == IntType(8)

    def test_int_literal_with_unsigned_suffix(self):
        # §2.1: "255:int16 unsigned" — lexer merges qualifier into suffix
        r = check_one("255:int16 unsigned")
        assert isinstance(r, TIntLiteral)
        assert r.ty == IntType(16, frozenset({Qualifier.UNSIGNED}))

    def test_string_literal(self):
        r = check_one('"hello"')
        assert isinstance(r, TStringLiteral)
        assert r.ty == STRING

    def test_bool_literal(self):
        r = check_one("true")
        assert isinstance(r, TBoolLiteral)
        assert r.ty == BOOL


# --- §3.1 Let bindings ---

class TestLetBindings:
    """Spec §3.1: let bindings with type inference and annotations."""

    def test_let_infers_type_from_value(self):
        r = check_one("(let x 42)")
        assert isinstance(r, TLetForm)
        assert r.name == "x"
        assert r.type_ann == INT64

    def test_let_with_type_annotation(self):
        r = check_one("(let x :type int32 42:int32)")
        assert isinstance(r, TLetForm)
        assert r.type_ann == INT32

    def test_let_type_mismatch_raises(self):
        # Annotated as bool but value is int64
        with pytest.raises(TypeError_, match="type mismatch"):
            check_one("(let x :type bool 42)")

    def test_let_name_accessible_later(self):
        results = check_all("(let x 42) x")
        assert isinstance(results[1], TSymbol)
        assert results[1].ty == INT64
        assert results[1].name == "x"


# --- §3.1 Set (reassignment) ---

class TestSet:
    """Spec §3.1: set requires mutable bindings."""

    def test_set_immutable_raises(self):
        # All let bindings are immutable by default
        with pytest.raises(TypeError_, match="cannot reassign immutable"):
            check_all("(let x 42) (set x 43)")

    def test_set_undefined_raises(self):
        with pytest.raises(NameError_, match="undefined name"):
            check_one("(set x 42)")


# --- Name resolution ---

class TestNameResolution:
    """Lexical scoping and name resolution."""

    def test_undefined_name_raises(self):
        with pytest.raises(NameError_, match="undefined name: y"):
            check_one("y")

    def test_builtin_operators_defined(self):
        # +, -, *, / should be in scope
        results = check_all("(let x 10) (let y 20) (+ x y)")
        call = results[2]
        assert isinstance(call, TCallForm)
        assert call.ty == INT64

    def test_lambda_params_in_scope(self):
        r = check_one("(lambda (:args (x int64)) (:returns int64) x)")
        assert isinstance(r, TLambdaForm)
        assert r.body[0].ty == INT64

    def test_lambda_params_not_in_outer_scope(self):
        # x is defined inside the lambda, not accessible outside
        with pytest.raises(NameError_, match="undefined name: x"):
            check_all("(let f (lambda (:args (x int64)) (:returns int64) x)) x")


# --- §3.2 Lambda type checking ---

class TestLambda:
    """Spec §3.2: lambda type checking — params, return type, body."""

    def test_lambda_type_is_fn_type(self):
        r = check_one("(lambda (:args (a int64) (b int64)) (:returns int64) (+ a b))")
        assert isinstance(r, TLambdaForm)
        assert isinstance(r.ty, FnType)
        assert r.ty.params == (INT64, INT64)
        assert r.ty.ret == INT64

    def test_lambda_body_type_must_match_return(self):
        with pytest.raises(TypeError_, match="does not match"):
            check_one('(lambda (:args (x int64)) (:returns bool) x)')

    def test_lambda_no_return_type_defaults_to_unit(self):
        # No :returns means default return type is unit.
        # Body returning int64 is a type mismatch.
        with pytest.raises(TypeError_, match="does not match"):
            check_one("(lambda (:args (x int64)) x)")

    def test_let_binding_lambda_records_fn_type(self):
        results = check_all(
            "(let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b)))"
        )
        let_form = results[0]
        assert isinstance(let_form, TLetForm)
        assert isinstance(let_form.type_ann, FnType)
        assert let_form.type_ann.ret == INT64

    def test_call_lambda_checks_arg_types(self):
        results = check_all("""
            (let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b)))
            (add 1 2)
        """)
        call = results[1]
        assert isinstance(call, TCallForm)
        assert call.ty == INT64

    def test_call_wrong_arg_count_raises(self):
        with pytest.raises(TypeError_, match="expects 2 arguments"):
            check_all("""
                (let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b)))
                (add 1)
            """)

    def test_call_wrong_arg_type_raises(self):
        with pytest.raises(TypeError_, match="argument 1"):
            check_all("""
                (let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b)))
                (add true 2)
            """)


# --- §3.2 Captures ---

class TestCaptures:
    """Spec §3.2: explicit captures in closures."""

    def test_capture_resolves_from_outer_scope(self):
        results = check_all("""
            (let total 100)
            (let get-total (lambda (:capture (total)) (:returns int64) total))
        """)
        lam = results[1].value
        assert isinstance(lam, TLambdaForm)
        assert lam.captures == [("total", False)]

    def test_capture_undefined_raises(self):
        with pytest.raises(NameError_, match="undefined capture"):
            check_one("(lambda (:capture (x)) (:returns int64) x)")


# --- §3.3 Control flow ---

class TestControlFlow:
    """Spec §3.3: if, cond, match type checking."""

    def test_if_condition_must_be_bool(self):
        with pytest.raises(TypeError_, match="must be bool"):
            check_all("(let x 42) (if x 1 2)")

    def test_if_two_arm_type(self):
        results = check_all("(if true 1 2)")
        assert results[0].ty == INT64

    def test_if_one_arm_returns_unit(self):
        results = check_all("(if true 42)")
        assert results[0].ty == UNIT

    def test_if_branch_type_mismatch_raises(self):
        with pytest.raises(TypeError_, match="different types"):
            check_all('(if true 42 "hello")')

    def test_do_returns_last_expr_type(self):
        r = check_one("(do 1 2 3)")
        assert isinstance(r, TDoForm)
        assert r.ty == INT64


# --- §8 Effects system ---

class TestEffects:
    """Spec §8: effect declaration and checking."""

    def test_raise_in_pure_context_raises(self):
        # §8.3: no :with means pure — raising is an error
        with pytest.raises(EffectError, match="raising effect 'fail'"):
            check_one('(raise fail "oops")')

    def test_raise_in_effectful_lambda_ok(self):
        # §8.3: :with (fail) allows raise fail
        r = check_one(
            '(lambda (:args (x int64)) (:returns int64) (:with (fail)) (raise fail "bad"))'
        )
        assert isinstance(r, TLambdaForm)
        assert "fail" in r.effects

    def test_calling_effectful_from_pure_raises(self):
        # §8.3: calling a function with effects from a pure context is an error
        with pytest.raises(EffectError, match="missing"):
            check_all("""
                (let greet (lambda (:args (name string)) (:returns unit) (:with (io))
                  (println name)))
                (let pure-fn (lambda (:args (name string)) (:returns unit)
                  (greet name)))
            """)

    def test_calling_effectful_from_effectful_ok(self):
        results = check_all("""
            (let greet (lambda (:args (name string)) (:returns unit) (:with (io))
              (println name)))
            (let main (lambda (:args (name string)) (:returns unit) (:with (io))
              (greet name)))
        """)
        main_fn = results[1].value
        assert isinstance(main_fn, TLambdaForm)
        assert main_fn.effects == frozenset({"io"})

    def test_handle_makes_effects_available(self):
        # handle should add the handled effects to the body's context
        r = check_one('(handle (raise fail "err") (fail (msg) msg))')
        assert isinstance(r, THandleForm)

    def test_raise_type_is_never(self):
        # raise never returns — its type is never
        r = check_one(
            '(lambda (:returns never) (:with (fail)) (raise fail "boom"))'
        )
        assert isinstance(r, TLambdaForm)
        assert r.body[0].ty == NEVER


# --- Full pipeline: parse → check → inspect IR ---

class TestFullPipeline:
    """End-to-end: source text through parse and check, inspecting the typed IR."""

    def test_simple_arithmetic(self):
        results = check_all("""
            (let x 10)
            (let y 20)
            (+ x y)
        """)
        assert len(results) == 3
        assert results[0].type_ann == INT64
        assert results[1].type_ann == INT64
        assert results[2].ty == INT64  # call to + returns int64

    def test_function_definition_and_call(self):
        results = check_all("""
            (let double (lambda (:args (n int64)) (:returns int64) (+ n n)))
            (double 21)
        """)
        assert results[1].ty == INT64

    def test_nested_let_and_call(self):
        results = check_all("""
            (let a 5)
            (let b 10)
            (let sum (lambda (:args (x int64) (y int64)) (:returns int64) (+ x y)))
            (sum a b)
        """)
        assert results[3].ty == INT64

    def test_if_with_comparison(self):
        results = check_all("""
            (let x 42)
            (if (> x 0) 1 0)
        """)
        assert results[1].ty == INT64

    def test_effectful_program(self):
        """A small program with effects: function that does IO, called from main."""
        results = check_all("""
            (let greet (lambda (:args (name string)) (:returns unit) (:with (io))
              (println name)))
            (let main (lambda (:returns unit) (:with (io))
              (greet "world")))
        """)
        greet_ty = results[0].type_ann
        assert isinstance(greet_ty, FnType)
        assert greet_ty.effects == frozenset({"io"})

        main_ty = results[1].type_ann
        assert isinstance(main_ty, FnType)
        assert main_ty.effects == frozenset({"io"})


# --- Mutable let bindings ---

class TestMutableLet:
    """Mutable let bindings with :mut keyword."""

    def test_mutable_let_allows_set(self):
        results = check_all("(let x :mut 42) (set x 43)")
        assert isinstance(results[0], TLetForm)
        assert isinstance(results[1], TSetForm)

    def test_mutable_let_with_type_ann(self):
        results = check_all("(let x :mut :type int64 42) (set x 43)")
        assert results[0].type_ann == INT64

    def test_set_type_mismatch_on_mutable(self):
        with pytest.raises(TypeError_, match="type mismatch in set"):
            check_all('(let x :mut 42) (set x "hello")')

    def test_immutable_still_default(self):
        # Without :mut, set should still fail
        with pytest.raises(TypeError_, match="cannot reassign immutable"):
            check_all("(let x 42) (set x 43)")


# --- Polymorphic builtins ---

class TestPolymorphicBuiltins:
    """Arithmetic and comparison operators work with any numeric type."""

    def test_add_int32(self):
        results = check_all("(let a 1:int32) (let b 2:int32) (+ a b)")
        assert results[2].ty == INT32

    def test_add_float64(self):
        results = check_all("(let a 1.0) (let b 2.0) (+ a b)")
        assert results[2].ty == FLOAT64

    def test_add_float32(self):
        results = check_all("(let a 1.0:float32) (let b 2.0:float32) (+ a b)")
        assert results[2].ty == FLOAT32

    def test_add_int64_still_works(self):
        results = check_all("(+ 1 2)")
        assert results[0].ty == INT64

    def test_compare_int32(self):
        results = check_all("(let a 1:int32) (let b 2:int32) (> a b)")
        assert results[2].ty == BOOL

    def test_compare_float64(self):
        results = check_all("(let a 1.0) (let b 2.0) (> a b)")
        assert results[2].ty == BOOL

    def test_mixed_types_raise(self):
        with pytest.raises(TypeError_, match="matching types"):
            check_all("(let a 1:int32) (let b 2) (+ a b)")

    def test_non_numeric_raises(self):
        with pytest.raises(TypeError_, match="numeric arguments"):
            check_all('(+ true false)')

    def test_sub_int16(self):
        results = check_all("(let a 10:int16) (let b 3:int16) (- a b)")
        assert results[2].ty == INT16

    def test_mul_float64(self):
        results = check_all("(let a 2.0) (let b 3.0) (* a b)")
        assert results[2].ty == FLOAT64

    def test_lambda_with_int32_arithmetic(self):
        """Lambda using int32 arithmetic — proves polymorphic builtins work through function bodies."""
        results = check_all("""
            (let add32 (lambda (:args (a int32) (b int32)) (:returns int32) (+ a b)))
            (add32 1:int32 2:int32)
        """)
        assert results[1].ty == INT32


# --- Handle result type ---

class TestHandleResultType:
    """Handle form returns handler's type, not body's, when body always raises."""

    def test_handle_body_raises_returns_handler_type(self):
        # Body raises (type never), handler returns string → handle type is string
        r = check_one('(handle (raise fail "err") (fail (msg) msg))')
        assert isinstance(r, THandleForm)
        # handler body is `msg` which has type unit (handler params typed as unit for now)
        assert r.ty == UNIT

    def test_handle_body_no_raise_returns_body_type(self):
        # Body doesn't raise — handle type is body type
        r = check_one('(handle 42 (fail (msg) msg))')
        assert isinstance(r, THandleForm)
        assert r.ty == INT64
