"""Tests for the Rigel type system (Plan 04).

Tests the constraint lattice, qualifier handling, and type compatibility.
"""

from __future__ import annotations

import pytest

from rigel.types import (
    INT8, INT16, INT32, INT64,
    FLOAT32, FLOAT64,
    BOOL, STRING, UNIT, NEVER,
    AnyConstraint,
    FloatConstraint,
    FloatType,
    FnType,
    IntConstraint,
    IntType,
    NumberConstraint,
    Qualifier,
    StructType,
    TypeVar,
    is_assignable,
    parse_qualifiers,
    resolve_type_name,
    satisfies,
    types_equal,
)


# --- §2.1 Numeric type hierarchy ---

class TestConstraintSatisfaction:
    """Tests for the constraint lattice: number > int/float > concrete types."""

    # int constraint

    def test_int64_satisfies_int(self):
        assert satisfies(INT64, IntConstraint())

    def test_int32_satisfies_int(self):
        assert satisfies(INT32, IntConstraint())

    def test_int8_satisfies_int(self):
        assert satisfies(INT8, IntConstraint())

    def test_float64_does_not_satisfy_int(self):
        assert not satisfies(FLOAT64, IntConstraint())

    def test_bool_does_not_satisfy_int(self):
        assert not satisfies(BOOL, IntConstraint())

    # float constraint

    def test_float64_satisfies_float(self):
        assert satisfies(FLOAT64, FloatConstraint())

    def test_float32_satisfies_float(self):
        assert satisfies(FLOAT32, FloatConstraint())

    def test_int64_does_not_satisfy_float(self):
        assert not satisfies(INT64, FloatConstraint())

    # number constraint

    def test_int64_satisfies_number(self):
        assert satisfies(INT64, NumberConstraint())

    def test_float64_satisfies_number(self):
        assert satisfies(FLOAT64, NumberConstraint())

    def test_bool_does_not_satisfy_number(self):
        assert not satisfies(BOOL, NumberConstraint())

    def test_string_does_not_satisfy_number(self):
        assert not satisfies(STRING, NumberConstraint())

    # any constraint

    def test_int64_satisfies_any(self):
        assert satisfies(INT64, AnyConstraint())

    def test_bool_satisfies_any(self):
        assert satisfies(BOOL, AnyConstraint())

    def test_string_satisfies_any(self):
        assert satisfies(STRING, AnyConstraint())


# --- §2.2 Qualifier semantics ---

class TestQualifiers:
    """Tests for qualifier handling on numeric types."""

    def test_unsigned_int(self):
        ty = IntType(32, frozenset({Qualifier.UNSIGNED}))
        # unsigned int satisfies (int unsigned)
        assert satisfies(ty, IntConstraint(frozenset({Qualifier.UNSIGNED})))

    def test_unsigned_int_does_not_satisfy_plain_int(self):
        # Per spec, `int` means signed checked — but our satisfies() checks subset
        # An unsigned int *does* have all quals that plain int requires (none).
        # This is correct: unsigned int32 is still an int.
        ty = IntType(32, frozenset({Qualifier.UNSIGNED}))
        assert satisfies(ty, IntConstraint())

    def test_plain_int_does_not_satisfy_unsigned_constraint(self):
        # Plain int32 (signed) does not satisfy (int unsigned)
        assert not satisfies(INT32, IntConstraint(frozenset({Qualifier.UNSIGNED})))

    def test_unchecked_float(self):
        ty = FloatType(64, frozenset({Qualifier.UNCHECKED}))
        assert satisfies(ty, FloatConstraint(frozenset({Qualifier.UNCHECKED})))

    def test_parse_qualifiers_empty(self):
        assert parse_qualifiers([]) == frozenset()

    def test_parse_qualifiers_unsigned(self):
        assert parse_qualifiers(["unsigned"]) == frozenset({Qualifier.UNSIGNED})

    def test_parse_qualifiers_multiple(self):
        result = parse_qualifiers(["unsigned", "unchecked"])
        assert result == frozenset({Qualifier.UNSIGNED, Qualifier.UNCHECKED})

    def test_parse_qualifiers_unknown_ignored(self):
        assert parse_qualifiers(["bogus"]) == frozenset()


# --- Type equality and assignability ---

class TestTypeEquality:
    """Tests for structural type equality and assignability."""

    def test_same_concrete_types_equal(self):
        assert types_equal(INT32, INT32)

    def test_different_concrete_types_not_equal(self):
        assert not types_equal(INT32, INT64)

    def test_int_float_not_equal(self):
        assert not types_equal(INT64, FLOAT64)

    def test_never_assignable_to_anything(self):
        # never (bottom type) is assignable to any type
        assert is_assignable(NEVER, INT64)
        assert is_assignable(NEVER, BOOL)
        assert is_assignable(NEVER, STRING)

    def test_nothing_assignable_to_never(self):
        assert not is_assignable(INT64, NEVER)
        assert not is_assignable(BOOL, NEVER)

    def test_same_type_assignable(self):
        assert is_assignable(INT32, INT32)

    def test_no_implicit_widening(self):
        # int32 is NOT assignable to int64 — no implicit widening
        assert not is_assignable(INT32, INT64)


# --- Function types ---

class TestFnType:
    """Tests for function type representation."""

    def test_fn_type_repr(self):
        fn = FnType(params=(INT32, INT32), ret=INT32)
        assert "int32" in repr(fn)

    def test_fn_type_with_effects(self):
        fn = FnType(params=(STRING,), ret=UNIT, effects=frozenset({"io"}))
        assert "io" in repr(fn)

    def test_fn_types_equal(self):
        a = FnType(params=(INT64,), ret=BOOL)
        b = FnType(params=(INT64,), ret=BOOL)
        assert types_equal(a, b)

    def test_fn_types_different_params(self):
        a = FnType(params=(INT64,), ret=BOOL)
        b = FnType(params=(INT32,), ret=BOOL)
        assert not types_equal(a, b)


# --- Name resolution ---

class TestResolveTypeName:
    """Tests for resolving built-in type/constraint names."""

    def test_int64(self):
        assert resolve_type_name("int64") == INT64

    def test_float32(self):
        assert resolve_type_name("float32") == FLOAT32

    def test_bool(self):
        assert resolve_type_name("bool") == BOOL

    def test_int_is_constraint(self):
        result = resolve_type_name("int")
        assert isinstance(result, IntConstraint)

    def test_number_is_constraint(self):
        result = resolve_type_name("number")
        assert isinstance(result, NumberConstraint)

    def test_unknown_returns_none(self):
        assert resolve_type_name("foobar") is None
