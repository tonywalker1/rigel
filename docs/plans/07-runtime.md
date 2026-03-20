# Plan 07 — Runtime Library

**Status:** Elaborated (designed). Implementation deferred — the interpreter (Plan 09) does not
need a runtime library because it reuses Python's runtime.

## Purpose

C/C++ runtime library linked into compiled Rigel programs. Provides: checked arithmetic helpers,
ref-counted strings, closure representation, effect handler machinery (setjmp/longjmp frames),
and panic/abort. The interpreter gets all of this for free from Python, so this library is only
needed when codegen (Plan 06) is implemented.

## Spec Sections

- §5 (Memory Model) — ownership, RAII, ref counting
- §6 (Compilation to C) — runtime support for generated code
- §8 (Effects System) — non-local control flow via setjmp/longjmp
- §9 (Concurrency) — deferred (future runtime concern)

## Inputs

- `06-codegen-c.md` — defines what the generated C code expects from the runtime
- `04-type-system.md` — types that need runtime representation (strings, closures)
- `00-conventions.md` — style

## Interface Contract

### Source: `src/rigel/runtime/`

```
src/rigel/runtime/
├── rigel_rt.h           # Single public header — all generated C includes this
├── rigel_checked.h      # Checked arithmetic (inline functions / macros)
├── rigel_string.c/h     # Ref-counted string type
├── rigel_closure.c/h    # Closure representation (fn pointer + captured env)
├── rigel_effect.c/h     # Effect handler frames (setjmp/longjmp)
└── rigel_panic.c/h      # Panic/abort with message
```

### Public API (via `rigel_rt.h`)

**Checked arithmetic:**
```c
// One function per (op, type) pair. Panics on overflow.
int8_t   rigel_add_i8(int8_t a, int8_t b);
int16_t  rigel_add_i16(int16_t a, int16_t b);
int32_t  rigel_add_i32(int32_t a, int32_t b);
int64_t  rigel_add_i64(int64_t a, int64_t b);
// Similarly: rigel_sub_*, rigel_mul_*
// Division always checked for zero:
int64_t  rigel_div_i64(int64_t a, int64_t b);
int64_t  rigel_mod_i64(int64_t a, int64_t b);
```

**Strings:**
```c
typedef struct { char *data; size_t len; size_t refcount; } rigel_string_t;

rigel_string_t rigel_string_from_cstr(const char *s);
rigel_string_t rigel_string_concat(rigel_string_t a, rigel_string_t b);
void           rigel_string_retain(rigel_string_t s);
void           rigel_string_release(rigel_string_t s);
void           rigel_string_print(rigel_string_t s, FILE *out);
```

**Closures:**
```c
typedef struct {
    void *fn;        // function pointer (cast to appropriate signature at call site)
    void *env;       // pointer to captured environment (heap-allocated struct)
    size_t refcount;
} rigel_closure_t;

rigel_closure_t rigel_closure_create(void *fn, void *env, size_t env_size);
void            rigel_closure_retain(rigel_closure_t c);
void            rigel_closure_release(rigel_closure_t c);
```

**Effect handlers:**
```c
typedef struct rigel_effect_frame {
    jmp_buf buf;
    int effect_id;
    void *args;                          // pointer to effect arguments
    struct rigel_effect_frame *parent;   // linked list of active frames
} rigel_effect_frame_t;

void rigel_effect_push(rigel_effect_frame_t *frame);
void rigel_effect_pop(void);
_Noreturn void rigel_effect_raise(int effect_id, void *args);
```

**Panic:**
```c
_Noreturn void rigel_panic(const char *message);
// Prints message to stderr, calls abort().
```

## Design Decisions

### Ref counting, not tracing GC

For the initial runtime, reference counting is simpler and predictable. Each heap-allocated
value (strings, closures, captured environments) carries a refcount. `retain`/`release` calls
are inserted by codegen at scope boundaries (RAII pattern). Cycle detection is not implemented —
Rigel's immutable-by-default semantics and lack of mutable reference types make cycles rare.

### Why C, with optional C++ for internals?

Generated code is pure C (C11). The runtime implementation may use C++ internally for:
- Persistent data structures (hash-array mapped tries for maps/vectors)
- Atomics and threading primitives (C++ `<atomic>`, `<thread>`)
- RAII wrappers for internal resource management

The public API (`rigel_rt.h`) is always C-compatible (`extern "C"` if compiled as C++).

### Checked arithmetic as inline functions

Using `__builtin_add_overflow` (GCC/Clang) provides both the overflow check and the result in
one operation. These are small enough to inline. Fallback for non-GCC compilers can use
explicit range checks.

### Effect frames as a thread-local stack

`rigel_effect_push/pop` maintain a thread-local linked list of `jmp_buf` frames. `raise` walks
the stack to find the matching handler. This is simple and correct for single-threaded programs.
For concurrency (§9), each thread/fiber would maintain its own effect frame stack.

## Error Cases

| Condition | Behavior |
|-----------|----------|
| Integer overflow (checked) | `rigel_panic("integer overflow")` → stderr + `abort()` |
| Division by zero | `rigel_panic("division by zero")` → stderr + `abort()` |
| Unhandled effect (no frame matches) | `rigel_panic("unhandled effect: <id>")` → stderr + `abort()` |
| String allocation failure | `rigel_panic("out of memory")` → stderr + `abort()` |

## Test Oracle

The runtime library is tested indirectly through compiled Rigel programs (test_codegen.py /
test_examples.py). Direct unit tests for the runtime are C tests, deferred until codegen is
implemented.

| Scenario | Expected |
|----------|----------|
| `rigel_add_i64(INT64_MAX, 1)` | Panic: integer overflow |
| `rigel_div_i64(10, 0)` | Panic: division by zero |
| `rigel_string_from_cstr("hello")` → print → release | "hello" printed, memory freed |
| Effect raise with matching handler | Handler body executed, returns value |
| Effect raise with no handler | Panic: unhandled effect |

## Known Gaps (deferred)

- **Persistent data structures** — lists, maps, vectors (§7 Collections). Needed for real
  programs but not for initial codegen.
- **Concurrency primitives** — fibers, channels, select (§9). Requires significant runtime
  infrastructure.
- **Cycle detection** — if mutable references are added, ref counting needs a cycle collector.
- **Custom allocators** — the runtime uses `malloc`/`free` throughout. Configurable allocators
  are a future optimization.

## Regeneration Instructions

- Generate files under `src/rigel/runtime/`.
- `rigel_rt.h` is the single include for generated C code — it includes all sub-headers.
- Checked arithmetic functions use `__builtin_add_overflow` etc. (GCC/Clang extension).
- String type is a simple ref-counted struct with `retain`/`release`.
- Closure type stores a void function pointer + void environment pointer.
- Effect frames use `setjmp.h`. Thread-local stack via `_Thread_local` (C11) or
  `__thread` (GCC extension).
- `rigel_panic` prints to stderr and calls `abort()`.
- All public functions are `extern "C"` compatible.
