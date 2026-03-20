"""Semantic analysis for Rigel.

Walks the parsed AST and produces a checked IR with resolved types and names.
Checks:
- Name resolution (lexical scoping)
- Type checking (annotations, literal defaults, assignment compatibility)
- Effect checking (raise vs :with declarations)

The checked IR mirrors the AST but every expression node carries a resolved type.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rigel.ast import (
    BoolLiteral,
    CallForm,
    CondForm,
    DoForm,
    HandleForm,
    IfForm,
    IntLiteral,
    FloatLiteral,
    LambdaForm,
    LetForm,
    MatchForm,
    Node,
    RaiseForm,
    SetForm,
    StringLiteral,
    Symbol,
    TypeForm,
)
from rigel.common import EffectError, NameError_, Span, TypeError_
from rigel.types import (
    BOOL,
    BUILTIN_TYPES,
    FLOAT64,
    INT64,
    NEVER,
    NeverType,
    STRING,
    UNIT,
    FnType,
    IntType,
    FloatType,
    Type,
    is_assignable,
)


# --- Checked IR nodes ---
# These mirror the AST but carry resolved type information.

@dataclass(frozen=True)
class TypedExpr:
    """Base for all checked IR nodes."""
    ty: Type
    span: Span


@dataclass(frozen=True)
class TIntLiteral(TypedExpr):
    value: int


@dataclass(frozen=True)
class TFloatLiteral(TypedExpr):
    value: float


@dataclass(frozen=True)
class TStringLiteral(TypedExpr):
    value: str


@dataclass(frozen=True)
class TBoolLiteral(TypedExpr):
    value: bool


@dataclass(frozen=True)
class TSymbol(TypedExpr):
    name: str


@dataclass(frozen=True)
class TLetForm(TypedExpr):
    name: str
    value: TypedExpr
    type_ann: Type | None
    mutable: bool


@dataclass(frozen=True)
class TSetForm(TypedExpr):
    name: str
    value: TypedExpr


@dataclass(frozen=True)
class TLambdaForm(TypedExpr):
    params: list[tuple[str, Type]]          # (name, type) pairs
    captures: list[tuple[str, bool]]        # (name, mut) pairs
    return_type: Type
    effects: frozenset[str]
    body: list[TypedExpr]


@dataclass(frozen=True)
class TIfForm(TypedExpr):
    condition: TypedExpr
    then_branch: TypedExpr
    else_branch: TypedExpr | None


@dataclass(frozen=True)
class TCondForm(TypedExpr):
    clauses: list[tuple[TypedExpr, TypedExpr]]
    else_clause: TypedExpr | None


@dataclass(frozen=True)
class TMatchForm(TypedExpr):
    target: TypedExpr
    arms: list[tuple[TypedExpr, TypedExpr]]     # (pattern, body) pairs


@dataclass(frozen=True)
class TCallForm(TypedExpr):
    func: TypedExpr
    args: list[TypedExpr]


@dataclass(frozen=True)
class TDoForm(TypedExpr):
    body: list[TypedExpr]


@dataclass(frozen=True)
class THandleForm(TypedExpr):
    body: TypedExpr
    handlers: list[tuple[str, list[str], TypedExpr]]  # (effect_name, param_names, handler_body)


@dataclass(frozen=True)
class TRaiseForm(TypedExpr):
    effect: str
    args: list[TypedExpr]


# --- Environment (lexical scope) ---

@dataclass
class Binding:
    """A name binding in the environment."""
    ty: Type
    mutable: bool = False


class Env:
    """Lexical scope environment — a stack of name→binding maps."""

    def __init__(self, parent: Env | None = None) -> None:
        self._bindings: dict[str, Binding] = {}
        self._parent = parent

    def define(self, name: str, ty: Type, mutable: bool = False) -> None:
        self._bindings[name] = Binding(ty=ty, mutable=mutable)

    def lookup(self, name: str) -> Binding | None:
        if name in self._bindings:
            return self._bindings[name]
        if self._parent is not None:
            return self._parent.lookup(name)
        return None

    def child(self) -> Env:
        return Env(parent=self)


# --- Built-in operator signatures ---

# Binary arithmetic: (+ a b), (- a b), (* a b), (/ a b)
_ARITH_OPS = {"+", "-", "*", "/", "mod"}
# Comparison: (< a b), (> a b), (<= a b), (>= a b), (= a b)
_CMP_OPS = {"<", ">", "<=", ">=", "=", "!="}
# Boolean: (and a b), (or a b), (not a)
_BOOL_OPS = {"and", "or"}


# --- Checker ---

class Checker:
    """Semantic analyzer: AST → checked IR.

    Tracks the current effect context (which effects are allowed).
    """

    def __init__(self) -> None:
        self.errors: list[Exception] = []
        self._effects: frozenset[str] = frozenset()     # currently allowed effects
        self._next_var_id = 0

    def check_program(self, nodes: list[Node]) -> list[TypedExpr]:
        """Check a list of top-level AST nodes."""
        env = Env()
        self._seed_builtins(env)
        return [self.check_node(node, env) for node in nodes]

    def check_node(self, node: Node, env: Env) -> TypedExpr:
        """Dispatch to the appropriate checker for a node type."""
        match node:
            case IntLiteral():
                return self._check_int_literal(node)
            case FloatLiteral():
                return self._check_float_literal(node)
            case StringLiteral():
                return TStringLiteral(ty=STRING, span=node.span, value=node.value)
            case BoolLiteral():
                return TBoolLiteral(ty=BOOL, span=node.span, value=node.value)
            case Symbol():
                return self._check_symbol(node, env)
            case LetForm():
                return self._check_let(node, env)
            case SetForm():
                return self._check_set(node, env)
            case LambdaForm():
                return self._check_lambda(node, env)
            case IfForm():
                return self._check_if(node, env)
            case CondForm():
                return self._check_cond(node, env)
            case MatchForm():
                return self._check_match(node, env)
            case CallForm():
                return self._check_call(node, env)
            case DoForm():
                return self._check_do(node, env)
            case HandleForm():
                return self._check_handle(node, env)
            case RaiseForm():
                return self._check_raise(node, env)
            case _:
                raise TypeError_(f"unsupported node type: {type(node).__name__}", node.span)

    # --- Literal checking ---

    def _check_int_literal(self, node: IntLiteral) -> TIntLiteral:
        if node.type_suffix:
            ty = self._resolve_type_suffix(node.type_suffix, node.span)
        else:
            ty = INT64  # spec: unadorned integer literal is int64
        return TIntLiteral(ty=ty, span=node.span, value=node.value)

    def _check_float_literal(self, node: FloatLiteral) -> TFloatLiteral:
        if node.type_suffix:
            ty = self._resolve_type_suffix(node.type_suffix, node.span)
        else:
            ty = FLOAT64  # spec: unadorned float literal is float64
        return TFloatLiteral(ty=ty, span=node.span, value=node.value)

    def _resolve_type_suffix(self, suffix: str, span: Span) -> Type:
        """Resolve a type suffix like 'int8' or 'int16 unsigned' to a Type."""
        parts = suffix.split()
        base_name = parts[0]
        quals_names = parts[1:]

        base = BUILTIN_TYPES.get(base_name)
        if base is None:
            raise TypeError_(f"unknown type in suffix: {base_name}", span)

        if quals_names:
            from rigel.types import parse_qualifiers
            quals = parse_qualifiers(quals_names)
            if isinstance(base, IntType):
                return IntType(bits=base.bits, quals=base.quals | quals)
            elif isinstance(base, FloatType):
                return FloatType(bits=base.bits, quals=base.quals | quals)

        return base

    # --- Name resolution ---

    def _check_symbol(self, node: Symbol, env: Env) -> TSymbol:
        # Keywords (like :type, :args) are not looked up
        if node.name.startswith(":"):
            return TSymbol(ty=UNIT, span=node.span, name=node.name)

        binding = env.lookup(node.name)
        if binding is None:
            raise NameError_(f"undefined name: {node.name}", node.span)
        return TSymbol(ty=binding.ty, span=node.span, name=node.name)

    # --- Let binding ---

    def _check_let(self, node: LetForm, env: Env) -> TLetForm:
        # Letrec: if binding a lambda with declared return type, pre-define the name
        # with a forward-declared FnType so the lambda body can reference itself.
        if isinstance(node.value, LambdaForm) and node.value.return_type is not None:
            param_types = []
            for p in node.value.params:
                pty = self._resolve_type_ann(p.type_ann)
                param_types.append(pty)
            ret_type = self._resolve_type_ann(node.value.return_type)
            declared_effects = frozenset(e.name for e in node.value.effects)
            forward_fn_type = FnType(params=tuple(param_types), ret=ret_type,
                                     effects=declared_effects)
            env.define(node.name.name, forward_fn_type, mutable=node.mutable)

        checked_value = self.check_node(node.value, env)

        if node.type_ann is not None:
            ann_type = self._resolve_type_ann(node.type_ann)
            if not is_assignable(checked_value.ty, ann_type):
                raise TypeError_(
                    f"type mismatch in let binding '{node.name.name}': "
                    f"expected {ann_type!r}, got {checked_value.ty!r}",
                    node.span,
                )
            bind_type = ann_type
        else:
            bind_type = checked_value.ty

        env.define(node.name.name, bind_type, mutable=node.mutable)
        return TLetForm(ty=UNIT, span=node.span, name=node.name.name,
                        value=checked_value, type_ann=bind_type, mutable=node.mutable)

    # --- Set (reassignment) ---

    def _check_set(self, node: SetForm, env: Env) -> TSetForm:
        binding = env.lookup(node.name.name)
        if binding is None:
            raise NameError_(f"undefined name: {node.name.name}", node.span)
        if not binding.mutable:
            raise TypeError_(
                f"cannot reassign immutable binding '{node.name.name}'",
                node.span,
            )

        checked_value = self.check_node(node.value, env)
        if not is_assignable(checked_value.ty, binding.ty):
            raise TypeError_(
                f"type mismatch in set '{node.name.name}': "
                f"expected {binding.ty!r}, got {checked_value.ty!r}",
                node.span,
            )

        return TSetForm(ty=UNIT, span=node.span, name=node.name.name, value=checked_value)

    # --- Lambda ---

    def _check_lambda(self, node: LambdaForm, env: Env) -> TLambdaForm:
        body_env = env.child()

        # Resolve parameter types
        param_types: list[tuple[str, Type]] = []
        for p in node.params:
            pty = self._resolve_type_ann(p.type_ann)
            param_types.append((p.name.name, pty))
            body_env.define(p.name.name, pty)

        # Resolve captures
        capture_info: list[tuple[str, bool]] = []
        for c in node.captures:
            binding = env.lookup(c.name.name)
            if binding is None:
                raise NameError_(f"undefined capture: {c.name.name}", c.span)
            body_env.define(c.name.name, binding.ty, mutable=c.mut)
            capture_info.append((c.name.name, c.mut))

        # Resolve return type
        ret_type: Type
        if node.return_type is not None:
            ret_type = self._resolve_type_ann(node.return_type)
        else:
            ret_type = UNIT  # default if no :returns

        # Resolve effects
        declared_effects = frozenset(e.name for e in node.effects)

        # Check body under this lambda's effect context
        prev_effects = self._effects
        self._effects = declared_effects
        checked_body = [self.check_node(b, body_env) for b in node.body]
        self._effects = prev_effects

        # Check that body's last expression type matches return type
        if checked_body:
            body_type = checked_body[-1].ty
            if not is_assignable(body_type, ret_type):
                raise TypeError_(
                    f"lambda body type {body_type!r} does not match "
                    f"declared return type {ret_type!r}",
                    node.span,
                )

        fn_type = FnType(
            params=tuple(t for _, t in param_types),
            ret=ret_type,
            effects=declared_effects,
        )

        return TLambdaForm(
            ty=fn_type, span=node.span,
            params=param_types, captures=capture_info,
            return_type=ret_type, effects=declared_effects,
            body=checked_body,
        )

    # --- If ---

    def _check_if(self, node: IfForm, env: Env) -> TIfForm:
        cond = self.check_node(node.condition, env)
        if not is_assignable(cond.ty, BOOL):
            raise TypeError_(f"if condition must be bool, got {cond.ty!r}", node.condition.span)

        then_ = self.check_node(node.then_branch, env)
        else_: TypedExpr | None = None
        result_type = then_.ty

        if node.else_branch is not None:
            else_ = self.check_node(node.else_branch, env)
            if not is_assignable(then_.ty, else_.ty) and not is_assignable(else_.ty, then_.ty):
                raise TypeError_(
                    f"if branches have different types: {then_.ty!r} vs {else_.ty!r}",
                    node.span,
                )
            # If one branch is never, the result type is the other branch's type
            if isinstance(then_.ty, type(NEVER)) and then_.ty == NEVER:
                result_type = else_.ty
            elif isinstance(else_.ty, type(NEVER)) and else_.ty == NEVER:
                result_type = then_.ty
        else:
            result_type = UNIT  # one-arm if returns unit

        return TIfForm(ty=result_type, span=node.span, condition=cond,
                        then_branch=then_, else_branch=else_)

    # --- Cond ---

    def _check_cond(self, node: CondForm, env: Env) -> TCondForm:
        checked_clauses: list[tuple[TypedExpr, TypedExpr]] = []
        result_type: Type | None = None

        for test_node, body_node in node.clauses:
            test = self.check_node(test_node, env)
            if not is_assignable(test.ty, BOOL):
                raise TypeError_(f"cond test must be bool, got {test.ty!r}", test_node.span)
            body = self.check_node(body_node, env)
            if result_type is None:
                result_type = body.ty
            checked_clauses.append((test, body))

        checked_else: TypedExpr | None = None
        if node.else_clause is not None:
            checked_else = self.check_node(node.else_clause, env)
            if result_type is None:
                result_type = checked_else.ty

        if result_type is None:
            result_type = UNIT

        return TCondForm(ty=result_type, span=node.span,
                         clauses=checked_clauses, else_clause=checked_else)

    # --- Match ---

    def _check_match(self, node: MatchForm, env: Env) -> TMatchForm:
        target = self.check_node(node.target, env)
        checked_arms: list[tuple[TypedExpr, TypedExpr]] = []
        result_type: Type | None = None

        for arm in node.arms:
            # For now, patterns are checked as expressions (literal matching)
            # Special case: _ is a wildcard pattern, not a name lookup
            if isinstance(arm.pattern, Symbol) and arm.pattern.name == "_":
                pat = TSymbol(ty=target.ty, span=arm.pattern.span, name="_")
            else:
                pat = self.check_node(arm.pattern, env)
            body = self.check_node(arm.body, env)
            if result_type is None:
                result_type = body.ty
            checked_arms.append((pat, body))

        if result_type is None:
            result_type = UNIT

        return TMatchForm(ty=result_type, span=node.span, target=target, arms=checked_arms)

    # --- Call ---

    def _check_call(self, node: CallForm, env: Env) -> TCallForm:
        # Check args first (needed for polymorphic dispatch)
        checked_args = [self.check_node(a, env) for a in node.args]

        # Try polymorphic builtin dispatch before general call checking
        if isinstance(node.func, Symbol) and not node.func.name.startswith(":"):
            poly_result = self._check_polymorphic_op(node.func.name, checked_args, node.span)
            if poly_result is not None:
                return poly_result

        func = self.check_node(node.func, env)

        if isinstance(func.ty, FnType):
            fn_ty = func.ty

            # Check argument count
            if len(checked_args) != len(fn_ty.params):
                raise TypeError_(
                    f"function expects {len(fn_ty.params)} arguments, "
                    f"got {len(checked_args)}",
                    node.span,
                )

            # Check argument types
            for i, (arg, expected) in enumerate(zip(checked_args, fn_ty.params)):
                if not is_assignable(arg.ty, expected):
                    raise TypeError_(
                        f"argument {i + 1}: expected {expected!r}, got {arg.ty!r}",
                        node.args[i].span,
                    )

            # Effect checking: callee's effects must be subset of our allowed effects
            if fn_ty.effects and not fn_ty.effects.issubset(self._effects):
                missing = fn_ty.effects - self._effects
                raise EffectError(
                    f"calling function with effects {fn_ty.effects} "
                    f"but current context only allows {self._effects}; "
                    f"missing: {missing}",
                    node.span,
                )

            return TCallForm(ty=fn_ty.ret, span=node.span, func=func, args=checked_args)

        # If we don't know the function type, fall through with a best-effort type
        return TCallForm(ty=UNIT, span=node.span, func=func, args=checked_args)

    # --- Do ---

    def _check_do(self, node: DoForm, env: Env) -> TDoForm:
        checked = [self.check_node(e, env) for e in node.body]
        result_type = checked[-1].ty if checked else UNIT
        return TDoForm(ty=result_type, span=node.span, body=checked)

    # --- Handle ---

    def _check_handle(self, node: HandleForm, env: Env) -> THandleForm:
        # The body runs with the handled effects added to the allowed set
        handled_effects = frozenset(h.effect.name for h in node.handlers)
        prev_effects = self._effects
        self._effects = self._effects | handled_effects

        checked_body = self.check_node(node.body, env)
        self._effects = prev_effects

        checked_handlers: list[tuple[str, list[str], TypedExpr]] = []
        for handler in node.handlers:
            handler_env = env.child()
            param_names = []
            for p in handler.params:
                handler_env.define(p.name.name, UNIT)  # handler params are untyped for now
                param_names.append(p.name.name)
            checked_handler_body = self.check_node(handler.body, handler_env)
            checked_handlers.append((handler.effect.name, param_names, checked_handler_body))

        # Result type: if the body type is `never` (always raises), the handle
        # form's type is the handler's return type. Otherwise, join body type
        # with handler types (for now, use first non-never type found).
        result_type = checked_body.ty
        if isinstance(result_type, NeverType):
            for _, _, handler_body in checked_handlers:
                if not isinstance(handler_body.ty, NeverType):
                    result_type = handler_body.ty
                    break

        return THandleForm(ty=result_type, span=node.span,
                           body=checked_body, handlers=checked_handlers)

    # --- Raise ---

    def _check_raise(self, node: RaiseForm, env: Env) -> TRaiseForm:
        effect_name = node.effect.name

        # Check that this effect is in the current allowed set
        if effect_name not in self._effects:
            raise EffectError(
                f"raising effect '{effect_name}' but current context "
                f"only allows: {self._effects or '(none — pure)'}",
                node.span,
            )

        checked_args = [self.check_node(a, env) for a in node.args]
        return TRaiseForm(ty=NEVER, span=node.span, effect=effect_name, args=checked_args)

    # --- Type annotation resolution ---

    def _resolve_type_ann(self, node: Node) -> Type:
        """Resolve a type annotation AST node to a Type."""
        if isinstance(node, Symbol):
            name = node.name
            ty = BUILTIN_TYPES.get(name)
            if ty is not None:
                return ty
            raise TypeError_(f"unknown type: {name}", node.span)

        # For now, only symbol type annotations are supported
        raise TypeError_(f"unsupported type annotation form: {type(node).__name__}", node.span)

    # --- Builtins ---

    def _seed_builtins(self, env: Env) -> None:
        """Add built-in operators and functions to the environment.

        Arithmetic and comparison operators are polymorphic — they accept any matching
        numeric types and resolve return types accordingly. Boolean and I/O operators
        have fixed types.
        """
        # Polymorphic operators are handled specially in _check_call via name lookup.
        # We seed them with a placeholder FnType so they're "defined" in scope,
        # but the actual type checking is done polymorphically at call sites.
        _placeholder_arith = FnType(params=(INT64, INT64), ret=INT64)
        _placeholder_cmp = FnType(params=(INT64, INT64), ret=BOOL)
        for op in _ARITH_OPS:
            env.define(op, _placeholder_arith)
        for op in _CMP_OPS:
            env.define(op, _placeholder_cmp)

        # Boolean operators are not polymorphic
        for op in _BOOL_OPS:
            env.define(op, FnType(params=(BOOL, BOOL), ret=BOOL))
        env.define("not", FnType(params=(BOOL,), ret=BOOL))

        # I/O (effectful)
        env.define("println", FnType(params=(STRING,), ret=UNIT, effects=frozenset({"io"})))
        env.define("print", FnType(params=(STRING,), ret=UNIT, effects=frozenset({"io"})))

    def _check_polymorphic_op(self, op_name: str, args: list[TypedExpr],
                               span: Span) -> TCallForm | None:
        """Handle polymorphic built-in operators.

        Returns a TCallForm if op_name is a polymorphic builtin, else None.
        Arithmetic ops: both args must be the same numeric type, result is that type.
        Comparison ops: both args must be the same numeric type, result is bool.
        """
        if op_name in _ARITH_OPS:
            if len(args) != 2:
                raise TypeError_(f"'{op_name}' expects 2 arguments, got {len(args)}", span)
            lhs, rhs = args[0].ty, args[1].ty
            if not isinstance(lhs, (IntType, FloatType)):
                raise TypeError_(f"'{op_name}' expects numeric arguments, got {lhs!r}", span)
            if not isinstance(rhs, (IntType, FloatType)):
                raise TypeError_(f"'{op_name}' expects numeric arguments, got {rhs!r}", span)
            if lhs != rhs:
                raise TypeError_(
                    f"'{op_name}' requires matching types, got {lhs!r} and {rhs!r}", span)
            return TCallForm(ty=lhs, span=span,
                             func=TSymbol(ty=FnType(params=(lhs, rhs), ret=lhs), span=span, name=op_name),
                             args=list(args))

        if op_name in _CMP_OPS:
            if len(args) != 2:
                raise TypeError_(f"'{op_name}' expects 2 arguments, got {len(args)}", span)
            lhs, rhs = args[0].ty, args[1].ty
            if not isinstance(lhs, (IntType, FloatType)):
                raise TypeError_(f"'{op_name}' expects numeric arguments, got {lhs!r}", span)
            if not isinstance(rhs, (IntType, FloatType)):
                raise TypeError_(f"'{op_name}' expects numeric arguments, got {rhs!r}", span)
            if lhs != rhs:
                raise TypeError_(
                    f"'{op_name}' requires matching types, got {lhs!r} and {rhs!r}", span)
            return TCallForm(ty=BOOL, span=span,
                             func=TSymbol(ty=FnType(params=(lhs, rhs), ret=BOOL), span=span, name=op_name),
                             args=list(args))

        return None


def check(nodes: list[Node]) -> list[TypedExpr]:
    """Check a list of top-level AST nodes. Raises on first error."""
    checker = Checker()
    return checker.check_program(nodes)
