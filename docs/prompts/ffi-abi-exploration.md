# Rigel FFI/ABI Design Exploration

You are helping design the foreign function interface (FFI) and application binary interface (ABI)
for Rigel, a strongly-typed, immutable-by-default, Scheme-derived language that compiles to C. The
full language specification is in `docs/rigel-spec.md`. Read it before proceeding.

## Context

Rigel must interoperate with the C and C++ ecosystem. The primary mechanism is a C-level FFI —
Rigel calls C functions directly, and C++ libraries are accessed through C shim/wrapper libraries.
This is the same strategy used by Rust, Zig, Nim, and others.

The design must address these dimensions (explore whichever dimension the user specifies):

### Dimension 1: Declaring Foreign Functions

How does Rigel declare external C functions? Consider:
- Syntax for `extern` declarations (types, calling conventions, variadic functions)
- How C header information maps to Rigel declarations
- Whether/how tooling could auto-generate declarations from C headers
- Grouping declarations (per-library modules vs. inline declarations)

### Dimension 2: Type Mapping

How do C types map to Rigel types? Consider:
- Primitive correspondence (`int32` ↔ `int32_t`, `float64` ↔ `double`, etc.)
- Pointers: opaque handles (`OpaquePtr<T>`) vs. typed pointers vs. raw addresses
- Strings: Rigel strings vs. `char*` — ownership, lifetime, encoding (UTF-8 guarantee?)
- Structs: C struct layout compatibility, packed/aligned structs
- Enums: C enum ↔ Rigel variant mapping
- `void*` and type erasure — how does Rigel's type system handle it?
- Nullable pointers vs. Rigel's option type

### Dimension 3: Callback Marshaling

How does Rigel pass functions to C code? Consider:
- Lambdas with no captures → bare C function pointers
- Lambdas with captures → function pointer + `void* user_data` pair (the universal C callback
  pattern)
- Who owns the capture environment? Preventing use-after-free.
- C libraries that store callbacks long-term (event loops, signal handlers) vs. short-lived
  callbacks (qsort comparators)
- Thread safety of captured state

### Dimension 4: Memory and Ownership Across the Boundary

Who owns what when data crosses the FFI boundary? Consider:
- Rigel-allocated memory passed to C (who frees it? when?)
- C-allocated memory received by Rigel (wrapping in RAII with `:release`?)
- Preventing double-free and use-after-free at the type level
- Buffer passing (slices/views vs. pointer+length pairs)
- How Qt-style parent-child ownership maps to Rigel's model

### Dimension 5: Effects and Safety

How does FFI interact with Rigel's purity and effect system? Consider:
- All FFI calls are effectful (I/O, mutation, foreign memory) — what effect annotation?
- Can the programmer assert a foreign function is pure? Should they?
- Error handling: C functions that return error codes vs. Rigel's effect-based errors
- Signal safety (C signals vs. Rigel's effect model)
- Undefined behavior quarantine — what guarantees does Rigel drop at the boundary?

### Dimension 6: ABI Stability and Compilation

How does Rigel's generated C code interface with foreign libraries at the linker level? Consider:
- Calling conventions (`cdecl`, platform defaults)
- Name mangling (or lack thereof — Rigel emits C, so no mangling by default)
- Static vs. dynamic linking implications
- Platform-specific ABI concerns (struct passing, register usage, alignment)
- How Rigel's monomorphization interacts with foreign generic-like patterns (e.g., `void*`-based
  C generics)

### Dimension 7: Ergonomics and Tooling

What does the developer experience look like? Consider:
- Binding generators (C headers → Rigel `extern` declarations)
- Wrapper libraries (hand-written idiomatic Rigel over raw bindings)
- Testing FFI code (mocking foreign functions via effect handlers?)
- Documentation conventions for FFI modules
- Error messages when types don't marshal correctly

## Ground Rules for Exploration

- Refer to what Rust, Zig, Nim, OCaml, and Haskell do — but don't blindly copy. Rigel's effect
  system and immutability defaults create different constraints.
- Prioritize safety at the boundary. The FFI is where Rigel's guarantees meet C's lack of
  guarantees. Be explicit about what breaks.
- Keep the syntax Scheme-flavored and consistent with existing Rigel forms.
- Think about the C shim pattern for C++ libraries as a first-class use case, not an
  afterthought.
- Consider both the common case (calling `malloc`/`free`, SQLite, POSIX) and the hard case (Qt,
  OpenGL, callback-heavy event loops).
