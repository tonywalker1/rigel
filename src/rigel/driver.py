"""CLI driver for Rigel: rigel run/check/compile."""

from __future__ import annotations

import argparse
import sys

from rigel.common import RigelEffect, RigelError


def _run_pipeline(args: argparse.Namespace) -> int:
    """Execute the parse → check → interpret/check-only pipeline."""
    from rigel.parser import parse
    from rigel.check import check
    from rigel.interp import interpret

    # Read source
    if args.file == "-":
        source = sys.stdin.read()
        filename = "<stdin>"
    else:
        try:
            with open(args.file) as f:
                source = f.read()
            filename = args.file
        except FileNotFoundError:
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 1
        except OSError as e:
            print(f"error: cannot read: {args.file}: {e}", file=sys.stderr)
            return 1

    # Parse
    try:
        ast = parse(source, filename)
    except RigelError as e:
        print(e, file=sys.stderr)
        return 1

    if getattr(args, "dump_ast", False):
        for node in ast:
            print(repr(node), file=sys.stderr)

    # Check
    try:
        ir = check(ast)
    except RigelError as e:
        print(e, file=sys.stderr)
        return 1

    if getattr(args, "dump_ir", False):
        for node in ir:
            print(repr(node), file=sys.stderr)

    # Interpret (run only)
    if args.command == "run":
        try:
            interpret(ir)
        except RigelError as e:
            print(e, file=sys.stderr)
            return 1
        except RigelEffect as e:
            print(f"unhandled effect: {e.effect}", file=sys.stderr)
            return 1

    return 0


def _compile_stub(args: argparse.Namespace) -> int:
    print("error: compile not yet implemented", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code (0 = success, 1 = error)."""
    parser = argparse.ArgumentParser(prog="rigel", description="Rigel language toolchain")
    parser.add_argument("--version", action="version", version="rigel 0.1.0")

    subparsers = parser.add_subparsers(dest="command")

    # run
    run_parser = subparsers.add_parser("run", help="Parse, check, and interpret a Rigel program")
    run_parser.add_argument("file", help="Rigel source file (or - for stdin)")
    run_parser.add_argument("--dump-ast", action="store_true", help="Print AST to stderr")
    run_parser.add_argument("--dump-ir", action="store_true", help="Print checked IR to stderr")

    # check
    check_parser = subparsers.add_parser("check", help="Parse and type-check a Rigel program")
    check_parser.add_argument("file", help="Rigel source file (or - for stdin)")
    check_parser.add_argument("--dump-ast", action="store_true", help="Print AST to stderr")
    check_parser.add_argument("--dump-ir", action="store_true", help="Print checked IR to stderr")

    # compile
    compile_parser = subparsers.add_parser("compile", help="Compile a Rigel program to C (not yet implemented)")
    compile_parser.add_argument("file", help="Rigel source file")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_usage(sys.stderr)
        return 1

    if args.command == "compile":
        return _compile_stub(args)

    return _run_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
