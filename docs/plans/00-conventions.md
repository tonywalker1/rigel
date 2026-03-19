# Plan 00 — Conventions

## Purpose

Defines shared conventions that all generated components follow. This plan is not generated into
a single file — it's guidance consumed by every other plan.

## Spec Sections

None directly. Cross-cutting.

## Decisions

### Project Layout

```
rigel/
├── docs/
│   ├── rigel-spec.md          # Language specification
│   ├── tutorial.md            # Tutorial
│   └── plans/                 # This directory — generation plans
├── src/
│   └── rigel/                 # Python package
│       ├── __init__.py
│       ├── ast.py             # 01-data-model
│       ├── lexer.py           # 02-lexer
│       ├── parser.py          # 03-parser
│       ├── types.py           # 04-type-system (future)
│       ├── check.py           # 05-semantic-analysis (future)
│       ├── codegen.py         # 06-codegen-c (future)
│       ├── runtime/           # 07-runtime (future, C/C++ sources)
│       ├── driver.py          # 08-driver (future)
│       └── interp.py          # 09-interpreter (future)
├── tests/
│   ├── conftest.py            # Shared fixtures
│   ├── test_lexer.py
│   ├── test_parser.py
│   └── ...
├── pyproject.toml             # Project metadata, pytest config
└── CLAUDE.md
```

### Error Handling

- All errors include source location (file, line, column).
- Errors are represented as a `RigelError` base class with subclasses per phase
  (`LexError`, `ParseError`, `TypeError`, `EffectError`).
- Errors carry a human-readable message and the source span that caused them.
- Multiple errors may be collected before aborting (where feasible), but the first phase to
  produce errors stops the pipeline.

### Source Locations

Every AST node and token carries a `Span`:
```python
@dataclass(frozen=True)
class Span:
    file: str       # source file path
    line: int       # 1-based
    col: int        # 1-based
    offset: int     # 0-based byte offset into source
    length: int     # byte length of the token/node
```

### Style

- Python 3.12+. Type hints on all public APIs.
- `@dataclass(frozen=True)` for all value types (AST nodes, tokens, spans, errors).
- No third-party dependencies in `src/`. Test dependencies (pytest) are the only externals.
- Functions over classes where there's no state to carry.

### Naming

- Modules: lowercase, short (`ast`, `lexer`, `parser`).
- AST node classes: PascalCase matching the Rigel form name (`LetForm`, `LambdaForm`, `TypeForm`).
- Test files mirror source: `test_lexer.py` tests `lexer.py`.

## Interface Contract

This plan defines no code interface — it defines conventions consumed by all other plans.

## Regeneration Instructions

This plan is not directly regenerated into code. It is included by reference in every other
plan's regeneration prompt.
