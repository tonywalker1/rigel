"""Tests for the Rigel interpreter (Plan 09).

Tests call the full pipeline: parse → check → interpret.
"""

import pytest
from io import StringIO

from rigel.parser import parse
from rigel.check import check
from rigel.interp import interpret
from rigel.common import RuntimeError_


def run(source: str, *, output: StringIO | None = None) -> object:
    """Parse, check, and interpret a Rigel source string."""
    ir = check(parse(source))
    return interpret(ir, output=output)


# --- Phase A: Literals ---

class TestLiterals:
    def test_int(self):
        assert run("42") == 42

    def test_float(self):
        assert run("3.14") == 3.14

    def test_string(self):
        assert run('"hello"') == "hello"

    def test_bool_true(self):
        assert run("true") is True

    def test_bool_false(self):
        assert run("false") is False


# --- Arithmetic ---

class TestArithmetic:
    def test_add(self):
        assert run("(+ 1 2)") == 3

    def test_sub(self):
        assert run("(- 10 3)") == 7

    def test_mul(self):
        assert run("(* 4 5)") == 20

    def test_int_div(self):
        # §: integer floor division
        assert run("(/ 10 3)") == 3

    def test_mod(self):
        assert run("(mod 10 3)") == 1

    def test_float_add(self):
        assert run("(+ 1.5 2.5)") == 4.0

    def test_float_div(self):
        assert run("(/ 7.0 2.0)") == 3.5

    def test_div_by_zero(self):
        with pytest.raises(RuntimeError_, match="division by zero"):
            run("(/ 10 0)")

    def test_mod_by_zero(self):
        with pytest.raises(RuntimeError_, match="division by zero"):
            run("(mod 10 0)")


# --- Comparison and Boolean ---

class TestComparison:
    def test_lt(self):
        assert run("(< 1 2)") is True

    def test_gt(self):
        assert run("(> 2 1)") is True

    def test_eq(self):
        assert run("(= 3 3)") is True

    def test_neq(self):
        assert run("(!= 3 4)") is True

    def test_le(self):
        assert run("(<= 3 3)") is True

    def test_ge(self):
        assert run("(>= 5 3)") is True

    def test_and(self):
        assert run("(and true false)") is False

    def test_or(self):
        assert run("(or true false)") is True

    def test_not(self):
        assert run("(not true)") is False


# --- Let Bindings ---

class TestLetBindings:
    def test_simple(self):
        assert run("(let x 10) x") == 10

    def test_two_bindings(self):
        assert run("(let x 10) (let y 20) (+ x y)") == 30

    def test_with_type_annotation(self):
        assert run("(let x :type int64 42) x") == 42

    def test_shadowing(self):
        # Inner let shadows outer
        assert run("(let x 1) (do (let x 2) x)") == 2


# --- If ---

class TestIf:
    def test_true_branch(self):
        assert run("(if true 1 2)") == 1

    def test_false_branch(self):
        assert run("(if false 1 2)") == 2

    def test_one_arm_true(self):
        assert run("(if true 42)") == 42

    def test_one_arm_false(self):
        assert run("(if false 42)") is None


# --- Cond ---

class TestCond:
    def test_first_match(self):
        assert run('(cond ((= 1 1) "yes") (:else "no"))') == "yes"

    def test_second_match(self):
        assert run('(cond ((= 1 2) "a") ((= 1 1) "b") (:else "c"))') == "b"

    def test_else(self):
        assert run('(cond ((= 1 2) "a") (:else "fallback"))') == "fallback"


# --- Match ---

class TestMatch:
    def test_literal_match(self):
        assert run('(match 1 (1 "one") (2 "two") (_ "other"))') == "one"

    def test_wildcard(self):
        assert run('(match 3 (1 "one") (2 "two") (_ "other"))') == "other"


# --- Do ---

class TestDo:
    def test_returns_last(self):
        assert run("(do 1 2 3)") == 3

    def test_with_bindings(self):
        assert run("(do (let x 5) (+ x 1))") == 6


# --- Lambda and Call ---

class TestLambda:
    def test_simple_function(self):
        src = "(let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b))) (add 3 4)"
        assert run(src) == 7

    def test_no_return_type(self):
        # Lambda with no :returns defaults to unit
        out = StringIO()
        src = '(let greet (lambda (:args (s string)) (:with (io)) (println s)))'
        # Just defining it, not calling — returns None (unit from let)
        assert run(src, output=out) is None

    def test_closure(self):
        src = """(let x 10)
(let add-x (lambda (:args (y int64)) (:capture (x)) (:returns int64) (+ x y)))
(add-x 5)"""
        assert run(src) == 15

    # Higher-order function types (-> int64 int64) not yet supported in type annotations.
    # Test deferred until function type annotation parsing is implemented.


# --- Recursion (letrec) ---

class TestRecursion:
    def test_factorial(self):
        src = """(let fact (lambda (:args (n int64)) (:returns int64)
  (if (= n 0) 1 (* n (fact (- n 1))))))
(fact 5)"""
        assert run(src) == 120

    def test_fibonacci(self):
        src = """(let fib (lambda (:args (n int64)) (:returns int64)
  (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2))))))
(fib 10)"""
        assert run(src) == 55

    def test_gcd(self):
        src = """(let gcd (lambda (:args (a int64) (b int64)) (:returns int64)
  (if (= b 0) a (gcd b (mod a b)))))
(gcd 48 18)"""
        assert run(src) == 6


# --- Effects ---

class TestEffects:
    def test_handle_raise(self):
        # §8: basic handle/raise
        assert run('(handle (raise fail "oops") (fail (msg) msg))') == "oops"

    def test_handle_no_raise(self):
        # Body doesn't raise — handler unused
        assert run("(handle 42 (fail (msg) 0))") == 42

    def test_nested_handle(self):
        src = """(handle
  (handle (raise fail "inner") (fail (msg) (raise fail "outer")))
  (fail (msg) msg))"""
        assert run(src) == "outer"

    def test_unhandled_effect(self):
        # The checker prevents raise in pure context, so we test unhandled effects
        # by directly invoking the interpreter with IR that raises in a handled context
        # where the inner handler re-raises an effect that isn't caught.
        # For now, test that calling an effectful function with handle works.
        src = '(let boom (lambda (:args) (:with (fail)) (raise fail "bang"))) (handle (boom) (fail (msg) msg))'
        assert run(src) == "bang"


# --- I/O ---

class TestIO:
    def test_println(self):
        out = StringIO()
        src = '(handle (do (println "hello")) (io (msg) msg))'
        run(src, output=out)
        assert out.getvalue() == "hello\n"

    def test_print_no_newline(self):
        out = StringIO()
        src = '(handle (do (print "hi")) (io (msg) msg))'
        run(src, output=out)
        assert out.getvalue() == "hi"

    def test_multiple_prints(self):
        out = StringIO()
        src = '(handle (do (println "a") (println "b")) (io (msg) msg))'
        run(src, output=out)
        assert out.getvalue() == "a\nb\n"
