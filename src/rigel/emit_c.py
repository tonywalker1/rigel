"""C code emitter for Rigel typed IR.

Translates TypedExpr nodes (output of the type checker) to a C translation unit.

Strategy:
- Top-level let-bound lambdas → C function definitions
- Top-level non-lambda expressions → statements in main()
- Algebraic effects:
    - io  → transparent; println/print map directly to printf
    - fail → setjmp/longjmp (single-level, non-resumable)
- Closures: only top-level lambdas are supported; self-captures (for recursion)
  are treated as references to the C-scope name and need no special handling.
- C code is written to a file; a separate compiler (gcc/clang) produces a binary.
"""

from __future__ import annotations

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
    TRaiseForm,
    TSetForm,
    TStringLiteral,
    TSymbol,
    TypedExpr,
)
from rigel.types import (
    BoolType,
    FloatType,
    FnType,
    IntType,
    NeverType,
    Qualifier,
    StringType,
    Type,
    UnitType,
)

# --- Operator tables ---

_BINOPS: dict[str, str] = {
    "+": "+", "-": "-", "*": "*", "/": "/", "mod": "%",
    "=": "==", "!=": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">=",
    "and": "&&", "or": "||",
}

_UNOPS: dict[str, str] = {
    "not": "!",
}

# --- Helpers ---

_C_KEYWORDS: frozenset[str] = frozenset({
    "auto", "break", "case", "char", "const", "continue", "default",
    "do", "double", "else", "enum", "extern", "float", "for", "goto",
    "if", "inline", "int", "long", "register", "restrict", "return",
    "short", "signed", "sizeof", "static", "struct", "switch", "typedef",
    "union", "unsigned", "void", "volatile", "while",
})


def _mangle(name: str) -> str:
    """Convert a Rigel identifier to a valid C identifier."""
    s = name.replace("-", "_").replace("?", "_p").replace("!", "_b")
    return ("_" + s) if s in _C_KEYWORDS else s


def _c_type(ty: Type) -> str:
    """Map a Rigel type to a C type string."""
    match ty:
        case IntType(bits=b, quals=q):
            prefix = "u" if Qualifier.UNSIGNED in q else ""
            return f"{prefix}int{b}_t"
        case FloatType(bits=32):
            return "float"
        case FloatType(bits=64):
            return "double"
        case BoolType():
            return "bool"
        case StringType():
            return "const char *"
        case UnitType():
            return "void"
        case _:
            return "/* unknown type */"


def _c_string(s: str) -> str:
    """Emit a C double-quoted string literal."""
    esc = (
        s.replace("\\", "\\\\")
         .replace('"', '\\"')
         .replace("\n", "\\n")
         .replace("\t", "\\t")
         .replace("\r", "\\r")
    )
    return f'"{esc}"'


# --- Emitter class ---

class _CEmitter:
    def __init__(self) -> None:
        self._tmp = 0
        self._needs_setjmp = False

    def _fresh(self) -> str:
        self._tmp += 1
        return f"_t{self._tmp}"

    # --- Top-level ---

    def emit_program(self, nodes: list[TypedExpr]) -> str:
        """Emit a complete C translation unit."""
        fn_defs: list[str] = []
        fwd_decls: list[str] = []
        main_stmts: list[str] = []

        for node in nodes:
            if isinstance(node, TLetForm) and isinstance(node.value, TLambdaForm):
                cname = _mangle(node.name)
                lam = node.value
                fwd_decls.append(self._forward_decl(cname, lam))
                fn_defs.append(self._emit_fn(cname, lam))
            else:
                out: list[str] = []
                val = self._emit_expr(node, out)
                main_stmts.extend(out)
                if val != "(void)0":
                    main_stmts.append(f"{val};")

        # Build output
        lines: list[str] = [
            "#include <stdio.h>",
            "#include <stdint.h>",
            "#include <stdbool.h>",
        ]
        if self._needs_setjmp:
            lines.append("#include <setjmp.h>")
            lines.extend([
                "",
                "/* fail effect infrastructure */",
                "static jmp_buf _rigel_fail_jmp;",
                "static const char *_rigel_fail_msg = NULL;",
            ])
        if fwd_decls:
            lines.append("")
            lines.extend(fwd_decls)
        for fn in fn_defs:
            lines.append("")
            lines.append(fn)
        lines.extend([
            "",
            "int main(void) {",
        ])
        for s in main_stmts:
            lines.append(f"    {s}")
        lines.extend([
            "    return 0;",
            "}",
            "",
        ])
        return "\n".join(lines)

    def _forward_decl(self, cname: str, lam: TLambdaForm) -> str:
        ret_ty = _c_type(lam.return_type)
        params = ", ".join(f"{_c_type(ty)} {_mangle(n)}" for n, ty in lam.params)
        return f"{ret_ty} {cname}({params or 'void'});"

    def _emit_fn(self, cname: str, lam: TLambdaForm) -> str:
        ret_ty = _c_type(lam.return_type)
        params = ", ".join(f"{_c_type(ty)} {_mangle(n)}" for n, ty in lam.params)
        body_stmts: list[str] = []
        last_expr = "(void)0"
        for expr in lam.body[:-1]:
            inner: list[str] = []
            val = self._emit_expr(expr, inner)
            body_stmts.extend(inner)
            if val != "(void)0":
                body_stmts.append(f"{val};")
        if lam.body:
            last_expr = self._emit_expr(lam.body[-1], body_stmts)
        lines = [f"{ret_ty} {cname}({params or 'void'}) {{"]
        for s in body_stmts:
            lines.append(f"    {s}")
        if not isinstance(lam.return_type, UnitType):
            lines.append(f"    return {last_expr};")
        lines.append("}")
        return "\n".join(lines)

    # --- Expression emitter ---

    def _emit_expr(self, node: TypedExpr, out: list[str]) -> str:
        """Emit node, appending any needed C statements to `out`.

        Returns a C expression string for the value.
        Returns the sentinel "(void)0" for unit-typed/statement-only nodes.
        """
        match node:
            case TIntLiteral(value=v):
                return f"{v}LL" if isinstance(node.ty, IntType) and node.ty.bits == 64 else str(v)
            case TFloatLiteral(value=v):
                return f"{v!r}f" if isinstance(node.ty, FloatType) and node.ty.bits == 32 else repr(v)
            case TStringLiteral(value=v):
                return _c_string(v)
            case TBoolLiteral(value=v):
                return "true" if v else "false"
            case TSymbol(name=name):
                return _mangle(name)

            case TLetForm(name=name, value=val):
                return self._emit_let(name, val, out)
            case TSetForm(name=name, value=val):
                val_expr = self._emit_expr(val, out)
                out.append(f"{_mangle(name)} = {val_expr};")
                return "(void)0"

            # Builtin io functions
            case TCallForm(func=TSymbol(name="println"), args=[arg]):
                arg_expr = self._emit_expr(arg, out)
                out.append(f'printf("%s\\n", {arg_expr});')
                return "(void)0"
            case TCallForm(func=TSymbol(name="print"), args=[arg]):
                arg_expr = self._emit_expr(arg, out)
                out.append(f'printf("%s", {arg_expr});')
                return "(void)0"

            # Binary operators
            case TCallForm(func=TSymbol(name=op), args=[a, b]) if op in _BINOPS:
                a_expr = self._emit_expr(a, out)
                b_expr = self._emit_expr(b, out)
                return f"({a_expr} {_BINOPS[op]} {b_expr})"

            # Unary operators
            case TCallForm(func=TSymbol(name=op), args=[a]) if op in _UNOPS:
                a_expr = self._emit_expr(a, out)
                return f"({_UNOPS[op]}{a_expr})"

            # General function call
            case TCallForm(func=func, args=args):
                func_expr = self._emit_expr(func, out)
                arg_exprs = [self._emit_expr(a, out) for a in args]
                call = f"{func_expr}({', '.join(arg_exprs)})"
                if isinstance(node.ty, UnitType):
                    out.append(f"{call};")
                    return "(void)0"
                return call

            case TIfForm(condition=cond, then_branch=then, else_branch=else_br):
                return self._emit_if(cond, then, else_br, out)
            case TCondForm(clauses=clauses, else_clause=else_clause):
                return self._emit_cond(clauses, else_clause, out)
            case TDoForm(body=body):
                return self._emit_do(body, out)
            case THandleForm(body=body, handlers=handlers):
                return self._emit_handle(body, handlers, out)
            case TRaiseForm(effect=eff, args=args):
                return self._emit_raise(eff, args, out)
            case _:
                return f"/* unsupported: {type(node).__name__} */"

    def _emit_let(self, name: str, val: TypedExpr, out: list[str]) -> str:
        val_expr = self._emit_expr(val, out)
        if isinstance(val.ty, (UnitType, FnType)):
            if val_expr != "(void)0":
                out.append(f"{val_expr};")
            return "(void)0"
        ty_str = _c_type(val.ty)
        out.append(f"{ty_str} {_mangle(name)} = {val_expr};")
        return "(void)0"

    def _emit_do(self, body: list[TypedExpr], out: list[str]) -> str:
        for expr in body[:-1]:
            inner: list[str] = []
            val = self._emit_expr(expr, inner)
            out.extend(inner)
            if val != "(void)0":
                out.append(f"{val};")
        if body:
            return self._emit_expr(body[-1], out)
        return "(void)0"

    def _emit_if(
        self,
        cond: TypedExpr,
        then: TypedExpr,
        else_br: TypedExpr | None,
        out: list[str],
    ) -> str:
        cond_expr = self._emit_expr(cond, out)

        # Try ternary: both branches must be side-effect-free single expressions
        then_stmts: list[str] = []
        then_expr = self._emit_expr(then, then_stmts)
        else_stmts: list[str] = []
        else_expr = "(void)0"
        if else_br is not None:
            else_expr = self._emit_expr(else_br, else_stmts)

        result_ty = (
            then.ty if not isinstance(then.ty, NeverType)
            else (else_br.ty if else_br else UnitType())
        )

        if not then_stmts and not else_stmts and else_br is not None:
            return f"({cond_expr} ? {then_expr} : {else_expr})"

        # Need block form
        if isinstance(result_ty, (UnitType, NeverType)) or else_br is None:
            out.append(f"if ({cond_expr}) {{")
            for s in then_stmts:
                out.append(f"    {s}")
            if then_expr != "(void)0":
                out.append(f"    {then_expr};")
            if else_br is not None:
                out.append("} else {")
                for s in else_stmts:
                    out.append(f"    {s}")
                if else_expr != "(void)0":
                    out.append(f"    {else_expr};")
            out.append("}")
            return "(void)0"

        tmp = self._fresh()
        out.append(f"{_c_type(result_ty)} {tmp};")
        out.append(f"if ({cond_expr}) {{")
        for s in then_stmts:
            out.append(f"    {s}")
        if then_expr != "(void)0":
            out.append(f"    {tmp} = {then_expr};")
        out.append("} else {")
        for s in else_stmts:
            out.append(f"    {s}")
        if else_expr != "(void)0":
            out.append(f"    {tmp} = {else_expr};")
        out.append("}")
        return tmp

    def _emit_cond(
        self,
        clauses: list[tuple[TypedExpr, TypedExpr]],
        else_clause: TypedExpr | None,
        out: list[str],
    ) -> str:
        result_ty = clauses[0][1].ty if clauses else (else_clause.ty if else_clause else UnitType())
        has_value = not isinstance(result_ty, (UnitType, NeverType))
        tmp = self._fresh() if has_value else None
        if has_value:
            out.append(f"{_c_type(result_ty)} {tmp};")
        for i, (test, body) in enumerate(clauses):
            test_stmts: list[str] = []
            test_expr = self._emit_expr(test, test_stmts)
            out.extend(test_stmts)
            prefix = "if" if i == 0 else "} else if"
            out.append(f"{prefix} ({test_expr}) {{")
            body_stmts: list[str] = []
            body_expr = self._emit_expr(body, body_stmts)
            for s in body_stmts:
                out.append(f"    {s}")
            if has_value and body_expr != "(void)0":
                out.append(f"    {tmp} = {body_expr};")
        if else_clause is not None:
            out.append("} else {")
            else_stmts: list[str] = []
            else_expr = self._emit_expr(else_clause, else_stmts)
            for s in else_stmts:
                out.append(f"    {s}")
            if has_value and else_expr != "(void)0":
                out.append(f"    {tmp} = {else_expr};")
        out.append("}")
        return tmp if has_value else "(void)0"

    def _emit_handle(
        self,
        body: TypedExpr,
        handlers: list[tuple[str, list[str], TypedExpr]],
        out: list[str],
    ) -> str:
        handler_map = {name: (params, hbody) for name, params, hbody in handlers}

        # io is transparent — println/print already map to printf
        if set(handler_map.keys()) == {"io"}:
            return self._emit_expr(body, out)

        # fail → setjmp/longjmp
        if "fail" in handler_map:
            self._needs_setjmp = True
            _, fail_body = handler_map["fail"]
            result_ty = body.ty
            has_value = not isinstance(result_ty, (UnitType, NeverType))
            tmp = self._fresh() if has_value else None
            if has_value:
                out.append(f"{_c_type(result_ty)} {tmp};")
            out.append("if (setjmp(_rigel_fail_jmp) == 0) {")
            body_stmts: list[str] = []
            body_expr = self._emit_expr(body, body_stmts)
            for s in body_stmts:
                out.append(f"    {s}")
            if has_value and body_expr != "(void)0":
                out.append(f"    {tmp} = {body_expr};")
            out.append("} else {")
            fail_stmts: list[str] = []
            fail_expr = self._emit_expr(fail_body, fail_stmts)
            for s in fail_stmts:
                out.append(f"    {s}")
            if has_value and fail_expr != "(void)0":
                out.append(f"    {tmp} = {fail_expr};")
            out.append("}")
            return tmp if has_value else "(void)0"

        # Unrecognized handler — just emit body
        return self._emit_expr(body, out)

    def _emit_raise(self, effect: str, args: list[TypedExpr], out: list[str]) -> str:
        if effect == "fail":
            if args:
                arg_stmts: list[str] = []
                arg_expr = self._emit_expr(args[0], arg_stmts)
                out.extend(arg_stmts)
                out.append(f"_rigel_fail_msg = {arg_expr};")
            out.append("longjmp(_rigel_fail_jmp, 1);")
            return "(void)0"
        out.append(f"/* raise {effect}: unhandled */")
        return "(void)0"


# --- Public API ---

def emit_c(nodes: list[TypedExpr]) -> str:
    """Emit a C translation unit from a list of checked IR nodes."""
    return _CEmitter().emit_program(nodes)
