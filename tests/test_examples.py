"""End-to-end example program tests (Plan 10, Slice 3).

Full programs: parse → check → interpret. Tests the complete pipeline.
"""

from io import StringIO

from rigel.parser import parse
from rigel.check import check
from rigel.interp import interpret


def run(source: str, *, output: StringIO | None = None) -> object:
    """Parse, check, and interpret a Rigel source string."""
    ir = check(parse(source))
    return interpret(ir, output=output)


class TestArithmeticProgram:
    def test_sum(self):
        src = """
(let a 10)
(let b 20)
(let sum (+ a b))
sum
"""
        assert run(src) == 30


class TestFunctionComposition:
    def test_compose(self):
        src = """
(let double (lambda (:args (x int64)) (:returns int64) (* x 2)))
(let add1 (lambda (:args (x int64)) (:returns int64) (+ x 1)))
(add1 (double 5))
"""
        assert run(src) == 11


class TestRecursiveGCD:
    def test_gcd(self):
        src = """
(let gcd (lambda (:args (a int64) (b int64)) (:returns int64)
  (if (= b 0) a (gcd b (mod a b)))))
(gcd 48 18)
"""
        assert run(src) == 6

    def test_gcd_coprime(self):
        src = """
(let gcd (lambda (:args (a int64) (b int64)) (:returns int64)
  (if (= b 0) a (gcd b (mod a b)))))
(gcd 17 13)
"""
        assert run(src) == 1


class TestEffectDrivenErrorHandling:
    def test_safe_div_zero(self):
        src = """
(let safe-div (lambda (:args (a int64) (b int64)) (:returns int64) (:with (fail))
  (if (= b 0)
    (raise fail "division by zero")
    (/ a b))))
(handle (safe-div 10 0) (fail (msg) -1))
"""
        assert run(src) == -1

    def test_safe_div_nonzero(self):
        src = """
(let safe-div (lambda (:args (a int64) (b int64)) (:returns int64) (:with (fail))
  (if (= b 0)
    (raise fail "division by zero")
    (/ a b))))
(handle (safe-div 10 2) (fail (msg) -1))
"""
        assert run(src) == 5


class TestNestedControlFlow:
    def test_classify(self):
        src = """
(let classify (lambda (:args (n int64)) (:returns string)
  (cond
    ((< n 0) "negative")
    ((= n 0) "zero")
    (:else "positive"))))
(classify -5)
"""
        assert run(src) == "negative"

    def test_classify_zero(self):
        src = """
(let classify (lambda (:args (n int64)) (:returns string)
  (cond
    ((< n 0) "negative")
    ((= n 0) "zero")
    (:else "positive"))))
(classify 0)
"""
        assert run(src) == "zero"

    def test_classify_positive(self):
        src = """
(let classify (lambda (:args (n int64)) (:returns string)
  (cond
    ((< n 0) "negative")
    ((= n 0) "zero")
    (:else "positive"))))
(classify 7)
"""
        assert run(src) == "positive"


class TestMultiFunction:
    def test_abs_then_double(self):
        src = """
(let abs (lambda (:args (n int64)) (:returns int64)
  (if (< n 0) (* n -1) n)))
(let double (lambda (:args (n int64)) (:returns int64) (* n 2)))
(double (abs -3))
"""
        assert run(src) == 6


class TestIOProgram:
    def test_hello_world(self):
        out = StringIO()
        src = '(handle (println "Hello, World!") (io (msg) msg))'
        run(src, output=out)
        assert out.getvalue() == "Hello, World!\n"

    def test_multi_line_output(self):
        out = StringIO()
        src = """
(handle
  (do
    (println "line 1")
    (println "line 2")
    (println "line 3"))
  (io (msg) msg))
"""
        run(src, output=out)
        assert out.getvalue() == "line 1\nline 2\nline 3\n"
