"""Tree-walking interpreter for Rigel.

Evaluates checked IR directly using Python's runtime. Values are Python natives
(int, float, str, bool, None) plus Closure and BuiltinFn dataclasses.

Effects are implemented as Python exceptions: raise → RigelEffect, handle → try/except.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable, TextIO

from rigel.check import (
    TBoolLiteral,
    TCallForm,
    TCondForm,
    TDoForm,
    TFloatLiteral,
    THandleForm,
    TIfForm,
    TIntLiteral,
    TLambdaForm,
    TLetForm,
    TMatchForm,
    TRaiseForm,
    TSetForm,
    TStringLiteral,
    TSymbol,
    TypedExpr,
)
from rigel.common import RigelEffect, RuntimeError_, Span

# --- Value types ---

Value = "int | float | str | bool | None | Closure | BuiltinFn"


@dataclass
class Closure:
    """A Rigel lambda captured at runtime."""
    params: list[str]
    body: list[TypedExpr]
    env: RuntimeEnv
    name: str | None = None


@dataclass
class BuiltinFn:
    """A built-in function."""
    name: str
    fn: Callable[..., object]


# --- Runtime environment ---

_SENTINEL = object()


class RuntimeEnv:
    """Maps names to values. Separate from the checker's Env (names → types)."""

    def __init__(self, parent: RuntimeEnv | None = None) -> None:
        self._bindings: dict[str, object] = {}
        self._mutables: set[str] = set()
        self._parent = parent

    def define(self, name: str, value: object, mutable: bool = False) -> None:
        self._bindings[name] = value
        if mutable:
            self._mutables.add(name)

    def lookup(self, name: str) -> object:
        if name in self._bindings:
            return self._bindings[name]
        if self._parent is not None:
            return self._parent.lookup(name)
        return _SENTINEL

    def set(self, name: str, value: object) -> bool:
        """Update an existing mutable binding. Returns True if found and updated."""
        if name in self._bindings:
            if name not in self._mutables:
                return False
            self._bindings[name] = value
            return True
        if self._parent is not None:
            return self._parent.set(name, value)
        return False

    def force_set(self, name: str, value: object) -> None:
        """Update a binding regardless of mutability (for letrec)."""
        if name in self._bindings:
            self._bindings[name] = value
        elif self._parent is not None:
            self._parent.force_set(name, value)

    def child(self) -> RuntimeEnv:
        return RuntimeEnv(parent=self)


# --- Built-in functions ---

def _seed_builtins(env: RuntimeEnv, output: TextIO) -> None:
    """Seed arithmetic, comparison, boolean, and I/O builtins."""

    def _arith(name: str, op: Callable) -> BuiltinFn:
        def fn(a: object, b: object) -> object:
            return op(a, b)
        return BuiltinFn(name=name, fn=fn)

    def _div(a: object, b: object) -> object:
        if b == 0:
            raise RuntimeError_("division by zero", _NO_SPAN)
        if isinstance(a, int) and isinstance(b, int):
            return a // b
        return a / b

    def _mod(a: object, b: object) -> object:
        if b == 0:
            raise RuntimeError_("division by zero", _NO_SPAN)
        return a % b

    import operator
    env.define("+", BuiltinFn(name="+", fn=operator.add))
    env.define("-", BuiltinFn(name="-", fn=operator.sub))
    env.define("*", BuiltinFn(name="*", fn=operator.mul))
    env.define("/", BuiltinFn(name="/", fn=_div))
    env.define("mod", BuiltinFn(name="mod", fn=_mod))

    env.define("<", BuiltinFn(name="<", fn=operator.lt))
    env.define(">", BuiltinFn(name=">", fn=operator.gt))
    env.define("<=", BuiltinFn(name="<=", fn=operator.le))
    env.define(">=", BuiltinFn(name=">=", fn=operator.ge))
    env.define("=", BuiltinFn(name="=", fn=operator.eq))
    env.define("!=", BuiltinFn(name="!=", fn=operator.ne))

    env.define("and", BuiltinFn(name="and", fn=lambda a, b: a and b))
    env.define("or", BuiltinFn(name="or", fn=lambda a, b: a or b))
    env.define("not", BuiltinFn(name="not", fn=lambda a: not a))

    def _println(s: object) -> None:
        output.write(str(s) + "\n")
        return None

    def _print(s: object) -> None:
        output.write(str(s))
        return None

    env.define("println", BuiltinFn(name="println", fn=_println))
    env.define("print", BuiltinFn(name="print", fn=_print))


# Placeholder span for builtin runtime errors
_NO_SPAN = Span(file="<builtin>", line=0, col=0, offset=0, length=0)


# --- Evaluator ---

def _eval(node: TypedExpr, env: RuntimeEnv) -> object:
    """Evaluate a single checked IR node."""
    match node:
        case TIntLiteral():
            return node.value
        case TFloatLiteral():
            return node.value
        case TStringLiteral():
            return node.value
        case TBoolLiteral():
            return node.value
        case TSymbol():
            val = env.lookup(node.name)
            if val is _SENTINEL:
                raise RuntimeError_(f"undefined name: {node.name}", node.span)
            return val
        case TLetForm():
            return _eval_let(node, env)
        case TSetForm():
            return _eval_set(node, env)
        case TIfForm():
            return _eval_if(node, env)
        case TCondForm():
            return _eval_cond(node, env)
        case TMatchForm():
            return _eval_match(node, env)
        case TDoForm():
            return _eval_do(node, env)
        case TLambdaForm():
            return _eval_lambda(node, env)
        case TCallForm():
            return _eval_call(node, env)
        case THandleForm():
            return _eval_handle(node, env)
        case TRaiseForm():
            return _eval_raise(node, env)
        case _:
            raise RuntimeError_(f"unsupported IR node: {type(node).__name__}", node.span)


def _eval_let(node: TLetForm, env: RuntimeEnv) -> None:
    # Letrec: if binding a lambda, pre-define for self-reference
    if isinstance(node.value, TLambdaForm):
        env.define(node.name, None, mutable=node.mutable)
        closure = _eval(node.value, env)
        if isinstance(closure, Closure):
            closure.name = node.name
        env.force_set(node.name, closure)
    else:
        val = _eval(node.value, env)
        env.define(node.name, val, mutable=node.mutable)
    return None


def _eval_set(node: TSetForm, env: RuntimeEnv) -> None:
    val = _eval(node.value, env)
    if not env.set(node.name, val):
        raise RuntimeError_(f"cannot reassign: {node.name}", node.span)
    return None


def _eval_if(node: TIfForm, env: RuntimeEnv) -> object:
    cond = _eval(node.condition, env)
    if cond:
        return _eval(node.then_branch, env)
    elif node.else_branch is not None:
        return _eval(node.else_branch, env)
    return None


def _eval_cond(node: TCondForm, env: RuntimeEnv) -> object:
    for test, body in node.clauses:
        if _eval(test, env):
            return _eval(body, env)
    if node.else_clause is not None:
        return _eval(node.else_clause, env)
    return None


def _eval_match(node: TMatchForm, env: RuntimeEnv) -> object:
    target = _eval(node.target, env)
    for pat, body in node.arms:
        # Wildcard: TSymbol with name "_"
        if isinstance(pat, TSymbol) and pat.name == "_":
            return _eval(body, env)
        pat_val = _eval(pat, env)
        if target == pat_val:
            return _eval(body, env)
    return None


def _eval_do(node: TDoForm, env: RuntimeEnv) -> object:
    result: object = None
    for expr in node.body:
        result = _eval(expr, env)
    return result


def _eval_lambda(node: TLambdaForm, env: RuntimeEnv) -> Closure:
    param_names = [name for name, _ in node.params]
    return Closure(params=param_names, body=node.body, env=env)


def _eval_call(node: TCallForm, env: RuntimeEnv) -> object:
    func = _eval(node.func, env)
    args = [_eval(a, env) for a in node.args]

    if isinstance(func, BuiltinFn):
        return func.fn(*args)
    elif isinstance(func, Closure):
        call_env = func.env.child()
        for pname, arg in zip(func.params, args):
            call_env.define(pname, arg)
        result: object = None
        for expr in func.body:
            result = _eval(expr, call_env)
        return result
    else:
        raise RuntimeError_(f"not callable: {func!r}", node.span)


def _eval_handle(node: THandleForm, env: RuntimeEnv) -> object:
    handler_map: dict[str, tuple[list[str], TypedExpr]] = {}
    for effect_name, param_names, handler_body in node.handlers:
        handler_map[effect_name] = (param_names, handler_body)

    try:
        return _eval(node.body, env)
    except RigelEffect as eff:
        if eff.effect in handler_map:
            param_names, handler_body = handler_map[eff.effect]
            handler_env = env.child()
            for pname, arg in zip(param_names, eff.effect_args):
                handler_env.define(pname, arg)
            return _eval(handler_body, handler_env)
        raise


def _eval_raise(node: TRaiseForm, env: RuntimeEnv) -> object:
    args = [_eval(a, env) for a in node.args]
    raise RigelEffect(node.effect, effect_args=args, span=node.span)


# --- Public API ---

def interpret(ir: list[TypedExpr], *, output: TextIO | None = None) -> object:
    """Evaluate a checked IR program. Returns the value of the last expression.

    output: stream for println/print builtins (defaults to sys.stdout).
    Raises RuntimeError_ on evaluation errors, RigelEffect on unhandled effects.
    """
    if output is None:
        output = sys.stdout

    env = RuntimeEnv()
    _seed_builtins(env, output)

    result: object = None
    for node in ir:
        try:
            result = _eval(node, env)
        except RigelEffect as eff:
            raise RuntimeError_(
                f"unhandled effect: {eff.effect}", eff.span,
            ) from eff

    return result
