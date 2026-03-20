"""Type system representation for Rigel.

Models the constraint-based type hierarchy from spec §2:
- Concrete types (int32, float64, bool, string, etc.) are leaves.
- Constraints (int, float, number) are interior nodes that match descendant types.
- Qualifiers (unsigned, unchecked, mut, unique, atomic) are composable modifiers.
- Function types (-> arg-types return-type) with effect annotations.
- User-defined types (opaque struct types with fields).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


# --- Qualifiers ---

class Qualifier(Enum):
    UNSIGNED = auto()
    UNCHECKED = auto()
    MUT = auto()
    UNIQUE = auto()
    ATOMIC = auto()


# Immutable qualifier set
Qualifiers = frozenset[Qualifier]

NO_QUALS: Qualifiers = frozenset()


def parse_qualifiers(names: list[str]) -> Qualifiers:
    """Convert qualifier name strings to a Qualifiers set."""
    mapping = {
        "unsigned": Qualifier.UNSIGNED,
        "unchecked": Qualifier.UNCHECKED,
        "mut": Qualifier.MUT,
        "unique": Qualifier.UNIQUE,
        "atomic": Qualifier.ATOMIC,
    }
    result = set()
    for name in names:
        if name in mapping:
            result.add(mapping[name])
    return frozenset(result)


# --- Types ---

@dataclass(frozen=True)
class Type:
    """Base for all types. Not instantiated directly."""


# Concrete numeric types

@dataclass(frozen=True)
class IntType(Type):
    """A concrete fixed-width integer type."""
    bits: int               # 8, 16, 32, 64
    quals: Qualifiers = field(default_factory=frozenset)

    def __repr__(self) -> str:
        name = f"int{self.bits}"
        if self.quals:
            qs = " ".join(q.name.lower() for q in sorted(self.quals, key=lambda q: q.name))
            return f"{name} {qs}"
        return name


@dataclass(frozen=True)
class FloatType(Type):
    """A concrete IEEE floating-point type."""
    bits: int               # 32, 64
    quals: Qualifiers = field(default_factory=frozenset)

    def __repr__(self) -> str:
        name = f"float{self.bits}"
        if self.quals:
            qs = " ".join(q.name.lower() for q in sorted(self.quals, key=lambda q: q.name))
            return f"{name} {qs}"
        return name


@dataclass(frozen=True)
class BoolType(Type):
    """The boolean type."""

    def __repr__(self) -> str:
        return "bool"


@dataclass(frozen=True)
class StringType(Type):
    """UTF-8 string type."""

    def __repr__(self) -> str:
        return "string"


@dataclass(frozen=True)
class UnitType(Type):
    """The unit type (void equivalent)."""

    def __repr__(self) -> str:
        return "unit"


@dataclass(frozen=True)
class NeverType(Type):
    """The bottom type — functions that never return (e.g., raise)."""

    def __repr__(self) -> str:
        return "never"


# Function types

@dataclass(frozen=True)
class FnType(Type):
    """Function type: (-> arg-types return-type)."""
    params: tuple[Type, ...]
    ret: Type
    effects: frozenset[str] = field(default_factory=frozenset)

    def __repr__(self) -> str:
        params = " ".join(repr(p) for p in self.params)
        eff = ""
        if self.effects:
            eff = f" (:with ({' '.join(sorted(self.effects))}))"
        return f"(-> {params} {self.ret!r}{eff})"


# User-defined types

@dataclass(frozen=True)
class StructType(Type):
    """A user-defined struct/record type."""
    name: str
    fields: tuple[tuple[str, Type], ...]    # (field_name, field_type) pairs
    opaque: bool = True

    def __repr__(self) -> str:
        return self.name


# Generic type variable (placeholder during type checking)

@dataclass(frozen=True)
class TypeVar(Type):
    """A type variable — stands for an unknown concrete type.

    Used during type inference for let bindings without annotations.
    """
    id: int

    def __repr__(self) -> str:
        return f"?T{self.id}"


# --- Constraints ---

@dataclass(frozen=True)
class Constraint:
    """A constraint that a type may satisfy."""


@dataclass(frozen=True)
class IntConstraint(Constraint):
    """Matches any fixed-width integer type with compatible qualifiers.

    `int` matches signed checked integers.
    `(int unsigned)` matches unsigned checked integers.
    """
    required_quals: Qualifiers = field(default_factory=frozenset)

    def __repr__(self) -> str:
        if self.required_quals:
            qs = " ".join(q.name.lower() for q in sorted(self.required_quals, key=lambda q: q.name))
            return f"(int {qs})"
        return "int"


@dataclass(frozen=True)
class FloatConstraint(Constraint):
    """Matches any IEEE float type with compatible qualifiers."""
    required_quals: Qualifiers = field(default_factory=frozenset)

    def __repr__(self) -> str:
        if self.required_quals:
            qs = " ".join(q.name.lower() for q in sorted(self.required_quals, key=lambda q: q.name))
            return f"(float {qs})"
        return "float"


@dataclass(frozen=True)
class NumberConstraint(Constraint):
    """Matches any numeric type (int or float)."""

    def __repr__(self) -> str:
        return "number"


@dataclass(frozen=True)
class AnyConstraint(Constraint):
    """Matches any type."""

    def __repr__(self) -> str:
        return "any"


# --- Constraint satisfaction ---

def satisfies(ty: Type, constraint: Constraint) -> bool:
    """Check if a concrete type satisfies a constraint.

    Returns True if `ty` is a valid instantiation of `constraint`.
    """
    if isinstance(constraint, AnyConstraint):
        return True

    if isinstance(constraint, NumberConstraint):
        return isinstance(ty, (IntType, FloatType))

    if isinstance(constraint, IntConstraint):
        if not isinstance(ty, IntType):
            return False
        # The type must have all qualifiers the constraint requires
        return constraint.required_quals.issubset(ty.quals)

    if isinstance(constraint, FloatConstraint):
        if not isinstance(ty, FloatType):
            return False
        return constraint.required_quals.issubset(ty.quals)

    return False


# --- Type compatibility ---

def types_equal(a: Type, b: Type) -> bool:
    """Structural type equality."""
    return a == b


def is_assignable(source: Type, target: Type) -> bool:
    """Check if a value of type `source` can be assigned where `target` is expected.

    For now this is strict equality. Widening (int32 -> int64) is not implicit.
    """
    if isinstance(source, NeverType):
        # Never is assignable to anything (divergent expression, including never itself)
        return True
    if isinstance(target, NeverType):
        # Nothing (except never) is assignable to never
        return False
    return types_equal(source, target)


# --- Built-in type constants ---

INT8 = IntType(8)
INT16 = IntType(16)
INT32 = IntType(32)
INT64 = IntType(64)
FLOAT32 = FloatType(32)
FLOAT64 = FloatType(64)
BOOL = BoolType()
STRING = StringType()
UNIT = UnitType()
NEVER = NeverType()


# --- Name-to-type resolution for type annotations ---

# Maps symbol names to concrete types or constraints
BUILTIN_TYPES: dict[str, Type] = {
    "int8": INT8,
    "int16": INT16,
    "int32": INT32,
    "int64": INT64,
    "float32": FLOAT32,
    "float64": FLOAT64,
    "bool": BOOL,
    "string": STRING,
    "unit": UNIT,
    "never": NEVER,
}

BUILTIN_CONSTRAINTS: dict[str, Constraint] = {
    "int": IntConstraint(),
    "float": FloatConstraint(),
    "number": NumberConstraint(),
    "any": AnyConstraint(),
}


def resolve_type_name(name: str) -> Type | Constraint | None:
    """Look up a built-in type or constraint by name.

    Returns None if the name is not a built-in.
    """
    if name in BUILTIN_TYPES:
        return BUILTIN_TYPES[name]
    if name in BUILTIN_CONSTRAINTS:
        return BUILTIN_CONSTRAINTS[name]
    return None
