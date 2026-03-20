# Plan 08 — Driver (CLI)

**Status:** Elaborated. To be implemented in Slice 3.

## Purpose

CLI entry point that orchestrates the Rigel pipeline: source → lex → parse → check →
interpret (or check-only). This is the user-facing command. For Slice 3, the driver supports
`run` (interpret) and `check` (type-check only) subcommands. A `compile` subcommand is
designed but deferred until codegen is implemented.

## Spec Sections

- All sections (pipeline orchestration)
- §6 (Compilation to C) — `compile` subcommand (deferred)

## Inputs

- `02-lexer.md` — tokenization (called internally by parser)
- `03-parser.md` — `parse()` entry point
- `05-semantic-analysis.md` — `check()` entry point
- `09-interpreter.md` — `interpret()` entry point
- `00-conventions.md` — error classes, style

## Interface Contract

### Source: `src/rigel/driver.py`

**Entry point:**
```python
def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code (0 = success, 1 = error).

    argv: command-line arguments (defaults to sys.argv[1:]).
    """
```

**Console script** (in `pyproject.toml`):
```toml
[project.scripts]
rigel = "rigel.driver:main"
```

### Subcommands

```
rigel run <file.rgl>       # Parse → check → interpret
rigel run -                 # Read from stdin
rigel check <file.rgl>     # Parse → check only (report errors, exit 0/1)
rigel compile <file.rgl>   # Parse → check → codegen (deferred — prints "not yet implemented")
```

### Flags

| Flag | Subcommands | Description |
|------|-------------|-------------|
| `--dump-ast` | run, check | Print parsed AST to stderr before checking |
| `--dump-ir` | run, check | Print checked IR to stderr before interpreting |
| `--version` | (global) | Print version and exit |

## Behavioral Requirements

### Pipeline

1. **Read source** — from file path or stdin (`-`).
2. **Parse** — call `parse(source, filename)`. On `ParseError`, print error and exit 1.
3. **Check** — call `check(ast)`. On `TypeError_`/`NameError_`/`EffectError`, print error and
   exit 1.
4. **Interpret** (run only) — call `interpret(ir)`. On `RuntimeError_`, print error and exit 1.
   On `RigelEffect` (unhandled effect reaching top level), print error and exit 1.
5. **Exit 0** on success.

### Error formatting

Errors are printed to stderr in the format:
```
<file>:<line>:<col>: <ErrorType>: <message>
```

This matches the format already provided by `RigelError.__str__()`.

### Dump modes

- `--dump-ast` prints a repr of each top-level AST node, one per line, to stderr.
- `--dump-ir` prints a repr of each top-level checked IR node, one per line, to stderr.
- Both can be combined. AST is printed before checking; IR is printed before interpreting.

### Stdin mode

`rigel run -` reads all of stdin as source text, with filename `<stdin>`.

## Error Cases

| Condition | Behavior |
|-----------|----------|
| No subcommand given | Print usage to stderr, exit 1 |
| File not found | Print `error: file not found: <path>` to stderr, exit 1 |
| File read error (permissions, etc.) | Print `error: cannot read: <path>: <reason>` to stderr, exit 1 |
| Parse error | Print error (with span), exit 1 |
| Type/name/effect error | Print error (with span), exit 1 |
| Runtime error | Print error (with span), exit 1 |
| `compile` subcommand used | Print `error: compile not yet implemented`, exit 1 |

## Test Oracle

| Command | Input | Expected |
|---------|-------|----------|
| `rigel run hello.rgl` | `(let x 42) x` | Exit 0, no output (no println) |
| `rigel run hello.rgl` | `(handle (do (println "hello") (raise io "test")) (io (msg) (println msg)))` | stdout: `hello\n`, exit 0 |
| `rigel check hello.rgl` | `(let x 42) x` | Exit 0, no output |
| `rigel check bad.rgl` | `(+ x 1)` | stderr: error about undefined `x`, exit 1 |
| `rigel run -` | stdin: `(+ 1 2)` | Exit 0 |
| `rigel run --dump-ast f.rgl` | `(let x 42)` | stderr: AST repr, exit 0 |
| `rigel run nofile.rgl` | — | stderr: file not found, exit 1 |
| `rigel compile f.rgl` | — | stderr: not yet implemented, exit 1 |
| `rigel --version` | — | stdout: `rigel 0.1.0`, exit 0 |

## Design Notes

### Why argparse?

Standard library, no dependencies, supports subcommands via `add_subparsers`. Sufficient for
the current command set.

### Why not print the final value?

`rigel run` is not a REPL. Programs produce output via `println`. The final expression's value
is discarded (like a script). A `rigel eval` or REPL mode could be added later.

### Console script entry point

The `pyproject.toml` entry `rigel = "rigel.driver:main"` means `pip install -e .` makes the
`rigel` command available. The `main()` function calls `sys.exit(main(sys.argv[1:]))` when
invoked as `__main__`.

## Regeneration Instructions

- Generate `src/rigel/driver.py`.
- Use `argparse` with subparsers for `run`, `check`, `compile`.
- Import `parse` from `rigel.parser`, `check` from `rigel.check`, `interpret` from
  `rigel.interp`.
- Import error classes from `rigel.common`.
- The `main()` function takes an optional `argv` parameter for testability.
- Add `if __name__ == "__main__": sys.exit(main())` guard.
- Update `pyproject.toml` to add `[project.scripts]` section.
