# Language Specification Draft — Working Title: "Rigel"

*A strongly-typed, immutable-by-default, Scheme-derived language designed for
AI-writable, human-readable code with first-class constraint-based generics.*

> **Status:** Exploratory draft. Everything is negotiable.

---

## 1. Design Principles

1. **S-expressions as universal syntax.** The source is a serialized AST. No
   ambiguous grammar, no operator precedence debates. Trivially parseable by
   both humans and LLMs.

2. **Explicit concrete types, abstract constraint names.** Concrete types name
   exactly what they are (`int32`, `float64`). Familiar short names (`int`,
   `float`, `number`) are constraint identifiers for generic programming.

3. **Immutable by default.** All bindings are immutable. Mutation requires
   explicit opt-in (`mut`).

4. **Safe by default.** Signed and checked arithmetic is the default.
   `unsigned` and `unchecked` are explicit qualifiers — and also constraints
   in the generic type system.

5. **Compilation target: C (initially).** The language transpiles to C for
   portability, debuggability, and access to existing toolchains. LLVM backend
   is a future option once semantics stabilize.

6. **One language, two forms.** The same syntax and semantics support both
   compiled and interpreted (REPL/eval) execution. Only the execution model
   differs.

7. **No type aliases.** There is no `typedef` or type aliasing. If you want
   a new name for an existing type, wrap it in a `type` form with an invariant
   or precondition. This eliminates bare aliases (which are technical debt)
   and nudges users toward encoding semantics. The language auto-generates
   default constructors, viewers, and release when not user-provided, keeping
   the wrapping cost minimal.

8. **Two tiers of data structures.** Persistent immutable collections (`list`,
   `vec`, `map`, `set`) for the functional core. Contiguous mutable containers
   (`array`, `buffer`) for performance-critical paths. The runtime may use C++
   for high-quality implementations of both.

9. **Declaration is separate from definition.** Naming (`let`) is orthogonal
   to what is being named (a value, a lambda, a type). This eliminates the
   asymmetries that arise when different kinds of definitions require different
   keywords. One keyword names things; value-expression forms describe what
   they are.

---

## 2. Type System

### 2.1 Numeric Type Hierarchy

The type system is rooted in a constraint hierarchy. Concrete types are leaves.
Constraint names are interior nodes that match any descendant.

```
number
├── int                          ; any fixed-width signed checked integer
│   ├── int8
│   ├── int16
│   ├── int32
│   └── int64                    ; ← default type for integer literals
├── (int unsigned)               ; any fixed-width unsigned checked integer
│   ├── int8 unsigned
│   ├── int16 unsigned
│   ├── int32 unsigned
│   └── int64 unsigned
├── (int unchecked)              ; any fixed-width signed unchecked integer
│   ├── int8 unchecked
│   ├── ...
├── (int unsigned unchecked)     ; any fixed-width unsigned unchecked integer
│   ├── int8 unsigned unchecked
│   ├── ...
├── float                        ; any IEEE float
│   ├── float32
│   └── float64                  ; ← default type for float literals
├── (float unchecked)            ; IEEE float, no NaN/Inf trapping
│   ├── float32 unchecked
│   └── float64 unchecked
├── rational                     ; (future) exact rational
└── complex                      ; (future) complex numbers
    ├── complex64                ; (float32 real + float32 imag)
    └── complex128               ; (float64 real + float64 imag)

bool                             ; NOT a number — explicit conversion required
                                 ; (bool->int b) -> 0 or 1
                                 ; (int->bool n) -> false if 0, true otherwise
```

**Literal defaults:** Unadorned `42` is `int64`. Unadorned `3.14` is `float64`.
Explicit suffixes narrow: `42:int8`, `255:int16 unsigned`, `3.14:float32`.

### 2.2 Qualifier Semantics

Qualifiers are not part of the type name — they are composable modifiers that
also serve as constraints in generic contexts.

**Arithmetic qualifiers** (apply to numeric types):

| Qualifier     | Default | Meaning |
|---------------|---------|---------|
| `signed`      | yes     | Two's complement signed representation |
| `unsigned`    | no      | Unsigned representation |
| `checked`     | yes     | Overflow/underflow traps at runtime (or compile-time when detectable) |
| `unchecked`   | no      | Overflow wraps (integers) or follows IEEE 754 silently (floats) |

**Ownership qualifiers** (apply to reference types and mutable bindings):

| Qualifier     | Default | Meaning |
|---------------|---------|---------|
| `unique`      | no      | Single owner; move semantics; no ref-count overhead |
| `atomic`      | no      | Ref-counted with atomic operations; safe to share across threads |

**Defaults are always the safe choice.** You opt into danger or performance explicitly:

```scheme
(let [x : int32] 42)                                ; signed, checked (safe default)
(let [y : int32 unsigned] 255)                       ; unsigned, checked
(let [z : int32 unchecked] 42)                       ; signed, wrapping on overflow
(let [w : int32 unsigned unchecked] 255)             ; unsigned, wrapping — "C-style"

(let [counter : int64 mut] 0)                        ; mutable, ref-counted (safe default)
(let [buf : (array float64 unique) mut] (array-new)) ; unique owner, no ref-count overhead
(let [shared : int64 atomic mut] 0)                  ; atomic ref-count, thread-safe
```

### 2.3 Constraint-Based Generics

Familiar short names (`int`, `float`, `number`) are **constraints**, not types.
They cannot be used to declare storage directly — only to constrain generic
type parameters.

```scheme
;; CONCRETE: fully specified, allocates exactly 4 bytes
(let add-saturating (lambda [a : int32] [b : int32]) -> int32
  (saturating-add a b))

;; GENERIC: int constraint — works for any signed checked integer
(let add (lambda [a : int] [b : int]) -> int
  (+ a b))

;; GENERIC: number constraint — works for any numeric type
(let sum (lambda [xs : (list number)]) -> number
  (fold + (cast 0 number) xs))
```

### 2.4 Type Labels (Scoped Type Variables)

Within a generic definition, you can **bind a name** to whatever concrete type
the caller provides. This is analogous to C++ template parameters or Haskell's
lowercase type variables, but explicit.

The syntax uses `as` to capture the resolved type:

```scheme
;; T is bound to whatever concrete type matches `int`
(let add (lambda [a : int as T] [b : T]) -> T
  (+ a b))

;; Multiple labels
(let convert (lambda [src : int as S] [dst-type : (type-of float as D)]) -> D
  (cast src D))

;; Label with compound constraint
(let hash-insert (lambda [k : (& hashable eq) as K]
                         [v : any as V]
                         [m : (map K V)]) -> (map K V)
  ...))
```

**Scoping rule:** A type label is visible from its introduction point to the
end of the enclosing form. Labels do not escape their defining scope.

### 2.5 User-Defined Types

Users define new concrete types using `type` inside a `let` binding. Types are
**opaque by default** — fields are not directly accessible from outside.
Interaction is through declared operations only (see §8b for full details).

```scheme
;; A concrete struct type — opaque by default
(let point2d (type
  [x : float64]
  [y : float64]

  :construct
  (let point (lambda [x : float64] [y : float64]) -> point2d
    (point2d x y))

  :viewers
  [(let x (lambda [self : point2d]) -> float64 (.x self))
   (let y (lambda [self : point2d]) -> float64 (.y self))]

  :methods
  [(let distance (lambda [self : point2d] [other : point2d]) -> float64
     (sqrt (+ (pow (- (.x other) (.x self)) 2.0)
              (pow (- (.y other) (.y self)) 2.0))))]))

;; An enum / tagged union
(let option (type [T]
  (some [value : T])
  (none)))

;; A user-defined numeric type that satisfies `number`
(let fixed-point-32 (type
  :opaque
  [raw : int32]
  :satisfies (number)

  :construct
  (let from-int (lambda [n : int32]) -> fixed-point-32
    (fixed-point-32 (* n 256)))    ; 8-bit fractional part

  :viewers
  [(let to-float (lambda [self : fixed-point-32]) -> float64
     (/ (int-to-float (.raw self)) 256.0))]

  :methods
  [(let add (lambda [self : fixed-point-32] [other : fixed-point-32])
       -> fixed-point-32
     (fixed-point-32 (+ (.raw self) (.raw other))))]))
```

Users can also define new **constraints** (analogous to type classes/traits):

```scheme
;; Define a constraint
(let serializable (constraint
  (serialize [self : Self]) -> (list int8 unsigned)
  (deserialize [data : (list int8 unsigned)]) -> Self))

;; Declare that a type satisfies it
(implement serializable for point2d
  (let serialize (lambda [self : point2d]) -> (list int8 unsigned)
    ...))
  (let deserialize (lambda [data : (list int8 unsigned)]) -> point2d
    ...)))
```

### 2.6 Constraint Composition

Constraints compose via intersection (`&`) and can be used anywhere a single
constraint can:

```scheme
;; K must satisfy both hashable and eq
(let lookup (lambda [k : (& hashable eq) as K]
                    [m : (map K any)]) -> (option any)
  ...))

;; Named compound constraint
(let map-key (constraint (& hashable eq comparable)))
```

---

## 3. Core Forms

### 3.1 Bindings With `let`

Rigel uses `let` to bind a name to a value. Naming (declaration) is separate
from what is being named (definition) — `let` handles the naming, and the
value expression describes what the thing is.

```scheme
;; Immutable binding: (let [name : type] value)
(let [x : int32] 42)

;; Mutable binding: mut qualifier inside the bracket
(let [counter : int64 mut] 0)

;; Reassignment of mutable: (set name value)
(set counter (+ counter 1))

;; Multiple bindings (scoped)
(let ([x : int32] 1
      [y : int32] 2)
  (+ x y))

;; Type inference permitted when unambiguous
(let [x] 42)            ; inferred as int64 (default literal type)
(let [x : int32] 42)    ; explicit — preferred style
```

**Disambiguation rules** (the parser checks structurally, no ambiguity in
S-expressions):

| Form | Meaning |
|------|---------|
| `(let [name : type] expr)` | Immutable binding |
| `(let [name : type mut] expr)` | Mutable binding |
| `(set name expr)` | Reassign existing mutable (compile error if immutable) |
| `(let name (lambda params...) -> type body...)` | Named function |
| `(let ([bindings...]) body...)` | Scoped let-block |

### 3.2 Functions and Closures

Functions are lambdas bound with `let`. There is no separate function keyword
— a "function" is a named lambda that does not capture state. A closure is a
lambda that captures bindings from its environment.

```scheme
;; Named function (a lambda bound to a name)
(let add (lambda [a : int32] [b : int32]) -> int32
  (+ a b))

;; Generic function with constraint
(let add (lambda [a : number as T] [b : T]) -> T
  (+ a b))

;; Anonymous lambda
(lambda [x : int32]) -> int32
  (* x x))

;; Higher-order function
(let apply-twice (lambda [f : (-> T T)] [x : any as T]) -> T
  (f (f x)))
```

**Closures and Explicit Captures**

Captures are declared explicitly using `:capture`. The compiler does not
silently close over variables — all captured state is visible in the lambda's
signature:

```scheme
;; No captures — a pure function
(let add (lambda [a : int32] [b : int32]) -> int32
  (+ a b))

;; Explicit capture — closes over `total`
(let [total : int64 mut] 0)
(let accumulate (lambda :capture [total mut] [value : int64]) -> int64
  (set total (+ total value))
  total))
```

Captures are listed after `:capture` and distinguished from arguments by the
absence of a type annotation — they close over an existing binding. The `mut`
qualifier on a capture allows mutation of the captured state. Without `mut`,
the capture is an immutable snapshot at the point of closure creation.

**Design rationale:** Explicit captures mean:
- The compiler knows exactly what's closed over — no escape analysis needed
- Stateful functions are just closures with mutable captures — no `static`
  keyword needed
- Captures are visible in the signature — readers see the full state shape

**Self-capture for recursion** is analogous to C++'s `this` pointer — a
recursive lambda captures its own binding:

```scheme
;; Self-referencing closure (recursive lambda)
(let factorial (lambda :capture [factorial] [n : int64]) -> int64
  (if (<= n 1)
    1
    (* n (factorial (- n 1))))))
```

**Function type syntax:** `(-> arg-types... return-type)`

```scheme
(-> int32 int32 int32)         ; takes two int32, returns int32
(-> (list T) T)                ; takes a list of T, returns T
```

### 3.3 Control Flow

```scheme
;; Conditional (expression, not statement — everything is an expression)
(if (> x 0)
  (+ x 1)
  (- x 1))

;; Pattern matching (primary dispatch mechanism)
(match value
  [(some x) (+ x 1)]
  [(none)   0])

(match x
  [0 "zero"]
  [1 "one"]
  [_ "other"])      ; _ is wildcard

;; Cond (multi-way conditional)
(cond
  [(< x 0) "negative"]
  [(= x 0) "zero"]
  [else     "positive"])
```

### 3.4 Iteration

No traditional loops. Recursion + tail-call optimization is the primary
mechanism. Standard higher-order functions for collection processing:

```scheme
;; Map, filter, fold — the workhorses
(map (lambda [x : int32]) -> int32 (* x 2)) my-list)
(filter (lambda [x : int32]) -> bool (> x 0)) my-list)
(fold + 0 my-list)

;; Explicit recursion (tail-call optimized)
(let factorial (lambda [n : int64]) -> int64
  (let go (lambda [acc : int64] [i : int64]) -> int64
    (if (<= i 1)
      acc
      (go (* acc i) (- i 1))))
  (go 1 n)))

;; For-each with side effects (returns unit)
(for-each (lambda [x : int32]) -> unit (print x)) my-list)
```

### 3.5 Data Structures

#### Persistent (Immutable) — The Default

```scheme
;; List (persistent linked list)
(let [xs : (list int32)] '(1 2 3 4))
(let [ys : (list int32)] (cons 0 xs))    ; xs is unchanged

;; Vec (persistent indexed — RRB-tree internally)
(let [v : (vec int32)] [1 2 3 4])
(let [w : (vec int32)] (assoc v 2 99))   ; v is unchanged, w has 99 at index 2

;; Map (persistent — HAMT internally)
(let [m : (map string int32)] {"alice" 1 "bob" 2})
(let [n : (map string int32)] (assoc m "carol" 3))

;; Set (persistent — HAMT internally)
(let [s : (set int32)] #{1 2 3})
```

#### Contiguous (Mutable) — Performance Path

`array` is a flat, contiguous memory region. It is a resource type with RAII
semantics — scope-bound, cache-friendly, and zero-overhead relative to C
arrays. The runtime implementation may use C++ (e.g., bounds-checked
`std::vector` or custom allocators).

```scheme
;; Fixed-size array — stack allocated when size is compile-time known
(let [pixels : (array int8 unsigned 1024)] (array-zero 1024))

;; Dynamic array — heap allocated, growable
(let [buf : (array int8 unsigned) mut] (array-new))
(array-push! buf 42)
(array-push! buf 43)
(let [len : int64] (array-length buf))
(let [val : int8 unsigned] (array-get buf 0))    ; bounds-checked by default

;; Unchecked access for inner loops (explicit opt-in to danger)
(let [val : int8 unsigned] (array-get-unchecked buf 0))

;; Slice — a fat pointer: (ptr, len, shared-ref-to-parent)
;; The shared reference keeps the parent's backing store alive for the slice's lifetime.
(let [window : (slice int8 unsigned)] (array-slice buf 10 20))

;; Array from persistent vec (copies into contiguous memory)
(let [flat : (array int32)] (array-from-vec my-vec))

;; Iterate contiguous memory (cache-friendly)
(array-for-each
  (lambda [i : int64] [val : int8 unsigned]) -> unit
    (process val))
  buf)
```

**Design notes on `array`:**

- Bounds-checked by default (`array-get`). Unchecked access via
  `array-get-unchecked` — same opt-in-to-danger pattern as arithmetic.
- Fixed-size arrays with compile-time-known length can be stack allocated.
- Dynamic arrays are heap-allocated and growable, similar to `std::vector`.
- Slices are fat pointers: `(pointer, length, shared-ref-to-parent)`. The shared
  reference to the parent prevents the backing store from being freed while any slice
  exists. If the parent array has `unique` ownership, the compiler promotes it to
  shared ownership at the point the slice is taken — no user annotation required.
- The runtime may use C++ internally for SIMD-friendly allocation, bounds
  checking, and growth strategies, while exposing a clean C ABI to generated
  code.

#### Buffer — Byte-Oriented I/O

```scheme
;; Buffer for I/O operations — contiguous, byte-oriented
(let [out : (buffer) mut] (buffer-new 4096))
(buffer-write! out b"HTTP/1.1 200 OK\r\n")
(buffer-write! out (serialize response))
(let [data : bytes] (buffer-freeze out))   ; immutable snapshot
```

---

## 3b. No Type Aliases — Wrapping With Invariants

Rigel has no `typedef`, `type alias`, or `newtype` without semantics. If you
want a new name for an existing type, you must wrap it — and the language
nudges you toward adding an invariant that justifies the new name.

The compiler auto-generates default constructor, viewers, and release when
not user-provided, so the wrapping cost is minimal:

```scheme
;; BAD (not possible in Rigel — no bare alias):
;; (typedef port-number int16 unsigned)

;; GOOD: wrap with an invariant — the compiler does the rest
(let port-number (type
  [value : int16 unsigned]
  :invariant (and (>= value 0) (<= value 65535))))

;; The compiler auto-generates:
;;   - constructor: (port-number 8080) -> port-number
;;       (raises fail if invariant violated)
;;   - viewer: (value pn) -> int16 unsigned
;;   - release: no-op (value type, no resources)

;; Usage
(let [http : port-number] (port-number 80))       ; ok
(let [bad  : port-number] (port-number 70000))     ; compile-time error (literal)
(let [dyn  : port-number] (port-number user-input)) ; runtime check, raises fail

;; Another example: positive integer
(let positive-int (type
  [value : int64]
  :invariant (> value 0)))

;; Non-empty string
(let non-empty-string (type
  [value : string]
  :invariant (> (str-length value) 0)))

;; Percentage (0.0 to 1.0)
(let proportion (type
  [value : float64]
  :invariant (and (>= value 0.0) (<= value 1.0))))
```

**Why this matters:**

- **No silent semantic confusion.** A `port-number` is not just a `uint16` —
  it has a valid range. The type system enforces this everywhere.
- **Compile-time checking when possible.** If the constructor argument is a
  literal, the compiler checks the invariant statically.
- **Runtime checking otherwise.** Dynamic values are checked at construction
  time, using the `fail` effect for violations.
- **Technical debt becomes visible.** If you find yourself writing
  `(let foo (type [value : int64]))` with no invariant, the absence of an
  invariant is a conscious choice, not an oversight.

---

## 4. Module System

```scheme
;; File: math/vector.rgl

(module math.vector
  :exports (vec2 dot cross magnitude normalize))

(let vec2 (type
  :opaque
  [x : float64]
  [y : float64]

  :construct
  (let vec2-new (lambda [x : float64] [y : float64]) -> vec2
    (vec2 x y))

  :viewers
  [(let x (lambda [self : vec2]) -> float64 (.x self))
   (let y (lambda [self : vec2]) -> float64 (.y self))]))

(let dot (lambda [a : vec2] [b : vec2]) -> float64
  (+ (* (x a) (x b))
     (* (y a) (y b)))))
```

```scheme
;; File: main.rgl

(import math.vector :as vec)
(import math.vector :only (dot cross))
(import io)

(let main (lambda) -> int32
  (let [a : vec.vec2] (vec.vec2-new 1.0 2.0))
  (let [b : vec.vec2] (vec.vec2-new 3.0 4.0))
  (io.println (dot a b))
  0))
```

---

## 5. Memory Model

### 5.1 Ownership Tiers

Rigel uses a tiered ownership model. The default is safe and invisible; performance
paths require explicit opt-in via qualifiers.

**Value types** (numbers, `bool`, `char`, small structs): copied by value. No
ownership machinery needed.

**Reference types** (persistent collections, strings, large structs, user-defined
types): **ref-counted by default**. The runtime maintains a reference count; the
last reference frees the allocation. This is invisible to the user — no explicit
memory management syntax. Immutable ref-counted data is inherently thread-safe:
nothing can mutate it, so it can be shared across threads with no locking.

Cycles in ref-counted data cannot occur at the immutable functional core: cycles
require mutation to construct, and persistent collections are immutable. For mutable
resource types with `:release`, RAII handles cleanup.

**Unique ownership** (`unique` qualifier): a single owner, no reference count, move
semantics. Ownership transfers on assignment. Use for performance-critical mutable
containers where ref-count overhead is unacceptable.

**Atomic shared ownership** (`atomic` qualifier): ref-counted with atomic operations;
safe to share mutable state across threads. Joins `unsigned` and `unchecked` as an
explicit opt-in to a different operational regime.

### 5.2 Thread Safety

The compiler enforces thread safety statically:

- **Immutable ref-counted data**: freely shareable across threads with no locking.
- **`mut` values** (non-atomic): may not cross a thread boundary. The compiler
  detects this statically and errors with a clear message naming two options:
  1. Transfer ownership: declare `unique` and move into the thread (single owner,
     no contention).
  2. Shared access: declare `atomic` (ref-counted with atomic operations).
- **`mut atomic` values**: explicitly thread-safe for shared mutable access.
  Higher-level coordination via channels — see §9.

### 5.3 Slices and Parent Lifetime

A `slice` is a fat pointer: `(pointer, length, shared-ref-to-parent)`. The shared
reference to the parent ensures the backing store lives as long as any slice into
it — slices can never become orphaned dangling pointers.

When the compiler detects a slice being taken from a `unique` array, it **promotes**
the array to shared ownership at compile time. No user annotation required.

### 5.4 No Null

Use `(option T)` everywhere. The generated C uses tagged unions.

---

## 6. Compilation to C

### 6.1 Type Mapping

| Rigel Type | C Type |
|------------|--------|
| `int8` | `int8_t` |
| `int32` | `int32_t` |
| `int64 unsigned` | `uint64_t` |
| `float32` | `float` |
| `float64` | `double` |
| `bool` | `_Bool` / `bool` |
| `(option T)` | `struct { _Bool has_value; T value; }` |
| `(list T)` | persistent linked list (ref-counted nodes) |
| `(vec T)` | persistent vector (RRB-tree, C++ runtime) |
| `(map K V)` | persistent hash map (HAMT, C++ runtime) |
| `(array T)` | `struct { T* data; size_t len; size_t cap; }` |
| `(array T N)` | `T data[N]` (stack-allocated, fixed size) |
| `(slice T)` | `struct { T* data; size_t len; }` (borrowed, no ownership) |
| `(buffer)` | `struct { uint8_t* data; size_t len; size_t cap; }` |
| `string` | UTF-8 byte array with length |

### 6.2 Checked Arithmetic

```c
// Generated C for: (+ a b) where a, b : int32
static inline int32_t rigel_add_i32_checked(int32_t a, int32_t b) {
    int32_t result;
    if (__builtin_add_overflow(a, b, &result)) {
        rigel_panic("integer overflow in addition");
    }
    return result;
}

// Generated C for: (+ a b) where a, b : int32 unchecked
static inline int32_t rigel_add_i32_unchecked(int32_t a, int32_t b) {
    return a + b;  // wraps per C semantics (with -fwrapv)
}
```

### 6.3 Immutability

```c
// (let [x : int32] 42) generates:
const int32_t x = 42;

// (let [y : int32 mut] 0) generates:
int32_t y = 0;
```

### 6.4 Generics (Monomorphization)

Generic functions are monomorphized at compile time (like C++ templates, Rust
generics). Each concrete instantiation generates a separate C function:

```c
// (add 1:int32 2:int32) generates a call to:
int32_t rigel_add__int32(int32_t a, int32_t b) { ... }

// (add 1:int64 2:int64) generates a call to:
int64_t rigel_add__int64(int64_t a, int64_t b) { ... }
```

### 6.5 Tail Call Optimization

Tail-recursive functions compile to loops:

```c
// factorial compiles to:
int64_t rigel_factorial(int64_t n) {
    int64_t acc = 1;
    int64_t i = n;
    while (i > 1) {
        acc = acc * i;  // or checked multiply
        i = i - 1;
    }
    return acc;
}
```

---

## 7. String Type

```scheme
;; UTF-8 string — immutable, length-prefixed
(let [name : string] "hello")

;; Byte string — raw bytes
(let [data : bytes] b"raw bytes here")

;; Char — a single Unicode scalar value (not a byte)
(let [c : char] 'λ')

;; String operations return new strings (immutable)
(let [greeting : string] (str-concat "hello, " name))
(let [upper : string] (str-upper name))
(let [len : int64] (str-length name))       ; character count, not byte count
(let [byte-len : int64] (str-byte-length name))
```

---

## 8. Effects System

### 8.1 The Problem Effects Solve

Consider three things a function might do beyond returning a value: fail with
an error, perform I/O, or yield intermediate results. In most languages, each
uses a different mechanism — exceptions, monads, callbacks, async/await — and
they don't compose well. Algebraic effects unify all of these under one model.

The key insight: **an effect is a request, not an action.** When a function
"performs" an effect, it's really saying "I need something from my caller." The
caller (via a handler) decides what actually happens. This is like the
Hollywood principle — "don't call us, we'll call you" — applied to control flow.

### 8.2 Defining Effects

Effects are declared like constraints — they name operations that must be
handled somewhere up the call stack:

```scheme
;; An effect is a set of operations that a function may perform
(let fail (effect
  (raise [msg : string]) -> never))

(let io (effect
  (read-file [path : string]) -> (result string io-error)
  (write-file [path : string] [data : string]) -> (result unit io-error)
  (println [msg : string]) -> unit))

(let yield (effect
  (yield [value : T]) -> unit))

(let ask (effect
  (ask) -> T))            ; like Reader monad — request a value from context
```

### 8.3 Performing Effects

Functions declare which effects they may perform using `with`:

```scheme
;; This function may fail and do I/O
(let read-config (lambda [path : string]) -> config
  :with (fail io)
  (let [content : string]
    (match (read-file path)
      [(ok s)   s]
      [(err e)  (raise (str-concat "cannot read: " path))]))
  (let [parsed : (result config string)]
    (parse-toml content))
  (match parsed
    [(ok cfg)  cfg]
    [(err msg) (raise msg)])))
```

The `:with` clause is part of the type signature. A function that performs
effects it doesn't declare is a compile error. A function with no `:with`
clause is **pure** — the type system guarantees it.

```scheme
;; Pure function — no effects, compiler enforces this
(let add (lambda [a : int64] [b : int64]) -> int64
  (+ a b))

;; This would be a compile error — println performs io:
;; (let sneaky (lambda [x : int64]) -> int64
;;   (io.println "side effect!")   ; ERROR: performs `io` but not declared
;;   x))
```

### 8.4 Handling Effects

Handlers intercept effects and decide what to do. This is where the power
lives — the same effectful code can be run with different handlers for
testing, logging, or production:

```scheme
;; Handle the `fail` effect by converting to result
(handle fail in
  (read-config "/etc/app.toml")
  :on
  [(raise msg) (err msg)])
;; returns: (result config string)

;; Handle `io` with real filesystem
(handle io in
  (read-config path)
  :on
  [(read-file p)      (os.read-file p)]
  [(write-file p d)   (os.write-file p d)]
  [(println msg)      (os.stdout.write-line msg)])

;; Handle `io` with mock for testing — same code, different handler
(handle io in
  (read-config "/etc/app.toml")
  :on
  [(read-file p)      (ok "[database]\nhost = \"localhost\"")]
  [(write-file p d)   (ok unit)]
  [(println msg)      unit])
```

### 8.5 Effect Composition

Effects compose naturally. A function with `:with (fail io yield)` can be
wrapped in handlers one at a time, peeling off layers:

```scheme
;; A pipeline that reads files, may fail, and yields intermediate results
(let process-files (lambda [paths : (list string)]) -> unit
  :with (fail io yield)
  (for-each
    (lambda [p : string]) -> unit
      :with (fail io yield)
      (let [content : string]
        (match (read-file p)
          [(ok s)   s]
          [(err e)  (raise (str-concat "failed: " p))]))
      (yield content))
    paths)))

;; Compose handlers — each peels off one effect layer
(handle yield in
  (handle fail in
    (handle io in
      (process-files '("a.txt" "b.txt"))
      :on [(read-file p)    (os.read-file p)]
          [(write-file p d) (os.write-file p d)]
          [(println msg)    (os.stdout.write-line msg)])
    :on [(raise msg) (io.eprintln msg)])
  :on [(yield content) (io.println (str-concat "got: " content))])
```

### 8.6 Why This Matters for Rigel

The effects system addresses your AI-coding thesis directly:

- **Rigor/structure:** Effects are declared in the type signature. You can see
  at a glance whether a function is pure, does I/O, or can fail. An LLM
  generating code must declare effects honestly — the compiler catches lies.

- **Testability:** The same code runs with real handlers in production and mock
  handlers in tests. No dependency injection frameworks, no mock libraries.

- **Readability:** A human scanning code sees `:with (fail io)` and
  immediately knows the "color" of the function. No hidden side effects.

### 8.7 Compilation to C

Effects compile to a continuation-passing style (CPS) transform or, more
practically for C, to setjmp/longjmp for simple cases and explicit handler
stacks for the general case:

```c
// Simplified: fail effect compiles to setjmp/longjmp
typedef struct {
    jmp_buf env;
    rigel_string_t error_msg;
} rigel_fail_handler_t;

// Thread-local handler stack
static _Thread_local rigel_fail_handler_t* fail_handler_stack = NULL;

// (raise msg) compiles to:
static _Noreturn void rigel_raise(rigel_string_t msg) {
    fail_handler_stack->error_msg = msg;
    longjmp(fail_handler_stack->env, 1);
}

// (handle fail in ... :on [(raise msg) expr]) compiles to:
rigel_fail_handler_t handler;
handler.next = fail_handler_stack;
fail_handler_stack = &handler;
if (setjmp(handler.env) == 0) {
    // normal path — run the body
    result = rigel_read_config(path);
} else {
    // effect was raised — run the handler
    rigel_string_t msg = handler.error_msg;
    result = /* handler expression using msg */;
}
fail_handler_stack = handler.next;
```

For more complex effects (yield, ask) that resume after handling, the compiler
generates coroutine-like state machines or uses platform-specific context
switching (ucontext on POSIX, fibers on Windows). This is where C++ in the
runtime could help — C++20 coroutines provide a clean substrate for resumable
effects.

### 8.8 Result Type (Still Available)

The `result` type remains as a data type for values. Effects and results are
complementary — `result` is a value you pass around, `fail` is a control flow
mechanism. A handler can convert between them:

```scheme
;; Convert effectful code to a result value
(let try-read-config (lambda [path : string]) -> (result config string)
  :with (io)
  (handle fail in
    (ok (read-config path))
    :on [(raise msg) (err msg)])))
```

---

## 8b. Opaque Types, Containment, and RAII

### 8b.1 No Direct Field Access

Types are **opaque by default**. There is no `.field` access syntax for
external code. All interaction with a type's internals goes through explicitly
defined operations:

```scheme
(let connection (type
  :opaque                         ; default, but explicit for clarity
  [handle : int64]
  [state  : (ref connection-state)]

  :construct
  (let connect (lambda [host : string] [port : int16 unsigned]) -> connection
    :with (fail io)
    (let [h : int64] (tcp-connect host port))
    (connection h (ref (connected)))))

  :methods
  [(let send (lambda [self : connection] [data : bytes]) -> (result int64 io-error)
     :with (io)
     ...))
   (let is-connected (lambda [self : connection]) -> bool
     (match (deref (.state self))    ; .field access only inside methods
       [(connected) true]
       [_           false])))]

  :release
  (lambda [self : connection]) -> unit
    :with (io)
    (tcp-close (.handle self)))))
```

**Inside methods:** `.field` access works — the type can see its own guts.

**Outside:** only the operations declared in `:methods` and `:construct` are
visible. The fields `handle` and `state` are completely hidden.

### 8b.2 RAII via `:release`

The `:release` block defines cleanup that runs automatically when a value
goes out of scope, analogous to C++ destructors and Rust's `Drop`:

```scheme
(let do-work (lambda [host : string]) -> unit
  :with (fail io)
  (let [conn : connection] (connect host 8080))
  ;; use conn...
  (send conn b"hello")
  ;; conn.release is called automatically here, even if (send) raised
  ))
```

The compiler inserts release calls at scope exit, including all early-exit
paths (effect raises, early returns). In the generated C, this means cleanup
code appears before every exit point, or uses the same setjmp/longjmp
mechanism as effects to ensure cleanup runs.

### 8b.3 Containment Over Inheritance

There is **no inheritance** in Rigel. Code reuse is through:

1. **Containment:** A type holds another type as a field and delegates
   through its methods.

2. **Constraints (type classes):** Shared behavior is defined through
   constraints. Multiple types can satisfy the same constraint without
   sharing implementation.

3. **Generic functions:** Write once, work on any type meeting the
   constraints.

```scheme
;; No inheritance — use containment + constraints

(let buffered-connection (type
  :opaque
  [inner : connection]
  [buffer : (mut-vec int8 unsigned)]

  :construct
  (let buffered-connect (lambda [host : string] [port : int16 unsigned])
      -> buffered-connection
    :with (fail io)
    (buffered-connection (connect host port) (mut-vec-new))))

  :methods
  [(let send (lambda [self : buffered-connection] [data : bytes])
       -> (result int64 io-error)
     :with (io)
     ;; buffer, then flush
     (push-all! (.buffer self) data)
     (when (> (length (.buffer self)) 4096)
       (flush self))
     (ok (byte-length data))))

   (let flush (lambda [self : buffered-connection]) -> (result unit io-error)
     :with (io)
     (let [result : (result int64 io-error)]
       (send (.inner self) (freeze (.buffer self))))
     (clear! (.buffer self))
     (match result
       [(ok _)  (ok unit)]
       [(err e) (err e)])))]

  :release
  (lambda [self : buffered-connection]) -> unit
    :with (io)
    ;; flush remaining, then inner connection cleans up automatically
    (ignore (flush self)))))
    ;; (.inner self) release is called automatically (nested RAII)
```

### 8b.4 The Viewer Pattern (Controlled Read Access)

Sometimes you need to expose data without exposing mutability. Rather than
making fields public, define **viewer** functions that return immutable
copies or computed values:

```scheme
(let sensor-reading (type
  :opaque
  [timestamp : int64 unsigned]
  [value     : float64]
  [quality   : int8 unsigned]

  :construct
  (let reading (lambda [ts : int64 unsigned] [val : float64] [q : int8 unsigned])
      -> sensor-reading
    (sensor-reading ts val q)))

  :viewers                           ; read-only projections
  [(let timestamp (lambda [self : sensor-reading]) -> int64 unsigned
     (.timestamp self)))
   (let value (lambda [self : sensor-reading]) -> float64
     (.value self)))
   (let is-valid (lambda [self : sensor-reading]) -> bool
     (> (.quality self) 50)))]))       ; computed, not raw field
```

Viewers are callable from outside but cannot modify the value. The distinction
from methods is semantic — viewers are guaranteed pure (no `:with` clause
allowed).

---

## 9. Concurrency

### 9.1 Concurrency as an Effect

Concurrency in Rigel is not a separate model bolted onto the language — it falls
out of the effect system and ownership rules. Spawning a task is a side effect,
so it belongs in the effect system:

```scheme
(let concurrent (effect
  (spawn [f : (-> T)]) -> (task T)
  (await [t : (task T)]) -> T
  (await-all [ts : (list (task T))]) -> (list T)))
```

A function that spawns work must declare `:with (concurrent)`. A function without
it is guaranteed single-threaded — the compiler enforces this.

### 9.2 Structured Concurrency via Effect Scoping

Effect handlers have lexical scope. A `spawn` effect cannot outlive its handler.
This gives structured concurrency as a language guarantee, not a library
discipline:

```scheme
(handle concurrent in
  (let a (spawn (fetch-users)))
  (let b (spawn (fetch-orders)))
  (merge-results (await a) (await b))
  ;; handler scope ends here — all spawned tasks
  ;; MUST be complete or cancelled. enforced statically.
  :on [(spawn f) (schedule-on-pool f)]
      [(await t) (block-until-complete t)]
      [(await-all ts) (block-until-all-complete ts)])
```

No orphan threads. No fire-and-forget escaping a scope. RAII/`:release` runs
even if a child task raises `fail`. This is what Trio (Python) and Java's
structured concurrency achieve as library discipline — in Rigel it is a compiler
guarantee from the effect system.

### 9.3 Main as a Task

A thread is a closure plus a path of execution. `main` is no different — it is
simply the task that receives the root `concurrent` handler from the runtime:

```scheme
(let main (lambda [args : (vec string)]) -> int32
  :with (io concurrent fail)
  (let server (spawn (listen config)))
  (let worker (spawn (process-queue queue)))
  (await-all (list server worker))
  0))
```

On a microcontroller with no OS threads, the `concurrent` handler runs tasks
cooperatively on a single core. On a server, it maps to a work-stealing thread
pool. Same source code, different handler.

### 9.4 Channels — Ownership-Aware Communication

Channels are the primary coordination primitive. The existing ownership system
enforces safety with no additional rules:

```scheme
(let producer (lambda [ch : (channel int32)]) -> unit
  :with (concurrent io)
  (loop [i 0]
    (channel-send ch i)
    (recur (+ i 1)))))

(let consumer (lambda [ch : (channel int32)]) -> unit
  :with (concurrent io)
  (loop []
    (let val (channel-recv ch))
    (log "got: {val}")
    (recur))))
```

**Safety from existing ownership rules:**

- Sending a `unique` value **moves** it through the channel — the sender cannot
  use it after send.
- Sending an immutable value is always safe — no mutation, no races.
- Sending a `mut` non-`atomic` value is a **compile error** — the compiler
  already catches this at thread boundaries (§5.2).

No new ownership rules needed. Channels inherit safety from the qualifier system.

### 9.5 Implicit Parallelism for Pure Functions

A function with no `:with` clause is **pure**. The compiler knows it cannot
observe side effects. This enables safe automatic parallelism:

```scheme
;; pure — no :with
(let expensive (lambda [x : int64]) -> int64
  (fib x))

;; explicit parallel map — compiler verifies purity of argument function
(let results (par-map data expensive))
```

`par-map` requires its function argument to be pure (no `:with` clause). This is
enforced by the type system — a function with effects cannot be passed to
`par-map`. This is something almost no other language can express: the type of
`par-map` encodes "this function must have no side effects" as a constraint.

The runtime decides whether parallelism is profitable (work vs. overhead). The
compiler provides the guarantee that parallelism is *safe*.

### 9.6 Concurrency Summary

| Concept | Rigel Mechanism |
|---|---|
| Spawning work | `spawn` — effect operation under `concurrent` |
| Scope/lifetime | Effect handler scope = structured concurrency |
| Communication | Channels, safety enforced by ownership qualifiers |
| Shared mutable state | `atomic` qualifier (§2.2, §5.1) |
| Ownership transfer | `unique` through channels (§5.1) |
| Pure parallelism | `par-map` — compiler verifies purity via absence of `:with` |
| Entry point | `main` is a task with the root `concurrent` handler |
| Bare metal | Different handler: cooperative single-thread scheduler |

**Design principle:** Concurrency is not a new model — it emerges from the
interaction of effects (for control flow), ownership qualifiers (for data
safety), and purity tracking (for implicit parallelism).

### 9.7 Compilation to C

Concurrency compiles using the same mechanisms as other effects:

- **`spawn`** creates a task descriptor. The handler determines scheduling
  (OS threads, green threads via `ucontext`/fibers, or cooperative coroutines).
- **`await`** suspends the current task. For non-resuming cases, this is a
  blocking call. For green threads, it yields the coroutine.
- **Channels** compile to lock-free queues (single-producer/single-consumer) or
  mutex-guarded queues depending on usage pattern. The C++ runtime provides
  high-quality implementations.
- **`par-map`** compiles to a work-stealing fork/join over a thread pool. The
  runtime sizes the pool to available cores.

The `concurrent` handler stack follows the same thread-local pattern as `fail`
handlers (§8.7), extended with task scheduling state.

---

## 10. Open Questions

### Resolved

1. **Bool is not a number.** `bool` is its own type outside the `number`
   hierarchy. Conversion is explicit: `(bool->int b)` / `(int->bool n)`.

2. **Default literal types:** `int64` for integer literals, `float64` for
   float literals. Explicit annotation narrows: `42:int8`, `3.14:float32`.

3. **No mutual recursion TCO in v0.1.** Direct tail recursion compiles to
   loops. Mutual recursion uses normal call stack. Keep it simple.

4. **Algebraic effects for control flow.** See §8 (expanded).

5. **File extension:** `.rgl`

6. **S-expressions kept as-is.** Parenthesis fatigue is accepted for now.
   Whitespace-sensitive syntax is rejected: a single space/indent change
   silently alters program structure, which is antithetical to AI-writability
   and the "source is a serialized AST" principle. Revisit only if fatigue
   proves genuinely problematic after reading real code.

7. **Memory model: ref-counted by default, opt-in to unique/atomic.** See §5.
   Reference types are ref-counted automatically (invisible to user). `unique`
   opts into single-owner move semantics (performance). `atomic` opts into
   atomic ref-counting for shared mutable state across threads. Slices are fat
   pointers holding a shared ref to their parent — they cannot be orphaned.

8. **Design principle: easy to use, hard to misuse.** Make illegal states
   unrepresentable. Every language mechanism should make the correct use the
   obvious default and the dangerous use require explicit opt-in. The type
   system enforces this statically wherever possible.

9. **Concurrency model.** Concurrency is an effect (`concurrent`), not a
   separate runtime model. Structured concurrency via effect handler scoping.
   Channels for communication (ownership-aware). `par-map` for pure parallel
   computation. Main is a task. See §9.

10. **One language, two forms.** Compiled and interpreted execution share
    identical syntax and semantics. There are no interpreter-only language
    features. The interpreter is the compiler minus the C emission step — it
    type-checks, monomorphizes, and executes in memory rather than emitting
    code. This makes the interpreter a natural test oracle for the compiler:
    same input must produce same output. If pressure to add dynamic features
    (e.g., `eval`) materializes in the future, the effect system provides a
    principled extension point without forking the language.

11. **Declaration separate from definition.** `let` binds names to values.
    There is no unified `def` keyword. Functions are lambdas bound with `let`.
    Types, constraints, and effects are value-like definitions bound with `let`.
    Reassignment uses `set`. This separation eliminates asymmetries between
    different kinds of definitions and makes the language more orthogonal.

12. **Unified function/closure model.** Functions and lambdas are the same
    construct — `lambda`. A "function" is a lambda with no captures. Closures
    use `:capture` to explicitly declare what they close over. Self-capture
    enables recursion. No separate `function` keyword or `static` keyword
    needed.

### Open

1. **Concurrency synchronization primitives — higher-level patterns.** The core
   model is settled (spawn/await/channels via effects, structured scoping). What
   remains: higher-level patterns like select/alt over multiple channels, task
   cancellation semantics, back-pressure on channels, and whether locks/mutexes
   are exposed at all or only channels.

2. **C++ in the runtime.** The generated output is C, but the Rigel runtime
   library (persistent data structures, ref counting, effect handlers,
   concurrency runtime) may use C++ where it simplifies implementation. The
   language boundary is the generated code, not the runtime.

3. **Dictionary-based parameter model.** An emerging design direction where the
   lambda parameter list (captures, arguments, and locals) forms a single
   dictionary — the function's complete state. Recursive self-calls would carry
   forward the full dictionary, updating only named entries. This would unify
   recursion and state management into one mechanism and enable named arguments
   as the norm. Needs careful design around: caller vs. self-call semantics,
   capture initialization, and shadowing/scoping rules.

4. **Named arguments.** If the parameter dictionary model is adopted, arguments
   would naturally be passed by name rather than position. This has implications
   for calling conventions, API evolution (adding/reordering params becomes
   non-breaking), and the distinction between external calls (must provide all
   typed args) and recursive self-calls (unspecified args carry forward).

---

## 11. Grammar (Preliminary EBNF)

```ebnf
program        = form* ;

form           = let-form | set-form | implement-form
               | module-form | import-form | expression ;

(* --- Bindings with `let` --- *)

let-form       = '(' 'let' let-body ')' ;

let-body       = binding expression                     (* immutable binding *)
               | IDENT lambda-expr                      (* named function *)
               | IDENT type-expr-form                   (* named type *)
               | IDENT constraint-expr                  (* named constraint *)
               | IDENT effect-expr                      (* named effect *)
               | IDENT expression                       (* named value *)
               | '(' binding+ ')' expression+ ;         (* scoped let-block *)

set-form       = '(' 'set' IDENT expression ')' ;       (* reassignment *)

binding        = '[' IDENT ':' type-expr qualifier* ']'
               | '[' IDENT ']' ;                         (* inferred type *)

(* --- Lambda (functions and closures) --- *)

lambda-expr    = '(' 'lambda' capture-clause? param* ')' '->' type-expr
                 effect-clause? expression+ ;

capture-clause = ':capture' capture+ ;
capture        = '[' IDENT qualifier* ']' ;              (* no type = capture *)

param          = '[' IDENT ':' type-expr label? ']' ;

label          = 'as' IDENT ;

effect-clause  = ':with' '(' IDENT+ ')' ;

(* --- Type definitions --- *)

type-expr-form = '(' 'type' type-params? type-body ')' ;
type-params    = '[' IDENT+ ']' ;                        (* generic type params *)
type-body      = field* type-sections?                   (* struct type *)
               | variant+ ;                              (* enum/tagged union *)

field          = '[' IDENT ':' type-expr ']' ;
variant        = '(' IDENT field* ')' ;

type-sections  = opaque? invariant? satisfies? construct? viewers? methods? release? ;
opaque         = ':opaque' ;
invariant      = ':invariant' expression ;
satisfies      = ':satisfies' '(' IDENT+ ')' ;
construct      = ':construct' let-form ;
viewers        = ':viewers' '[' let-form+ ']' ;
methods        = ':methods' '[' let-form+ ']' ;
release        = ':release' lambda-expr ;

(* --- Constraints and effects --- *)

constraint-expr = '(' 'constraint' method-sig+ ')'
                | '(' 'constraint' '(' '&' IDENT+ ')' ')' ;
method-sig     = '(' IDENT param* ')' '->' type-expr ;

effect-expr    = '(' 'effect' method-sig+ ')' ;

implement-form = '(' 'implement' IDENT 'for' IDENT let-form+ ')' ;

(* --- Module system --- *)

module-form    = '(' 'module' dotted-ident module-opts ')' ;
import-form    = '(' 'import' dotted-ident import-opts ')' ;

(* --- Types --- *)

type-expr      = concrete-type | constraint-type | compound-type ;

concrete-type  = base-type qualifier* ;
base-type      = 'int8' | 'int16' | 'int32' | 'int64'
               | 'float32' | 'float64'
               | 'bool' | 'char' | 'string' | 'bytes' | 'unit'
               | IDENT ;                        (* user-defined types *)

qualifier      = 'unsigned' | 'unchecked' | 'mut'    (* arithmetic / mutability *)
               | 'unique' | 'atomic' ;              (* ownership *)

constraint-type = 'int' | 'float' | 'number' | 'any'
               | '(' '&' constraint-type+ ')'   (* intersection *)
               | IDENT ;                         (* user-defined constraints *)

compound-type  = '(' type-constructor type-expr+ ')'
               | '(' type-constructor type-expr+ INTEGER ')'  (* sized: array *)
               | '(' '->' type-expr+ ')' ;       (* function types *)

type-constructor = 'list' | 'vec' | 'map' | 'set' | 'option' | 'result'
               | 'array' | 'slice' | 'buffer'
               | IDENT ;                         (* user-defined generics *)

(* --- Expressions --- *)

expression     = literal | IDENT | application | special-form ;

literal        = INTEGER (':' type-expr)?        (* optional type suffix *)
               | FLOAT (':' type-expr)?
               | STRING | CHAR | BOOL | 'unit' ;

application    = '(' expression expression* ')' ;

special-form   = let-form | set-form | if-form | match-form | cond-form
               | lambda-expr | handle-form | begin-form ;

if-form        = '(' 'if' expression expression expression ')' ;

match-form     = '(' 'match' expression match-clause+ ')' ;
match-clause   = '[' pattern expression ']' ;

pattern        = IDENT | literal | '_'
               | '(' IDENT pattern* ')' ;         (* constructor pattern *)

cond-form      = '(' 'cond' cond-clause+ ')' ;
cond-clause    = '[' expression expression ']'
               | '[' 'else' expression ']' ;

handle-form    = '(' 'handle' IDENT 'in' expression+ ':on' handler-clause+ ')' ;
handler-clause = '[' '(' IDENT IDENT* ')' expression ']' ;

begin-form     = '(' 'begin' expression+ ')' ;
```

---

## 12. Example Program

```scheme
;; file: main.rgl

(module main
  :exports (main))

(import io)
(import math.ops :only (clamp))

;; --- Constraints ---

(let printable (constraint
  (to-string [self : Self]) -> string))

;; --- Effects ---

(let log (effect
  (log-msg [level : string] [msg : string]) -> unit))

;; --- Types (opaque, with RAII) ---

(let rgb (type
  :opaque
  [r : int8 unsigned]
  [g : int8 unsigned]
  [b : int8 unsigned]

  :construct
  (let rgb-new (lambda [r : int8 unsigned]
                       [g : int8 unsigned]
                       [b : int8 unsigned]) -> rgb
    (rgb r g b))

  :viewers
  [(let r (lambda [self : rgb]) -> int8 unsigned (.r self)))
   (let g (lambda [self : rgb]) -> int8 unsigned (.g self)))
   (let b (lambda [self : rgb]) -> int8 unsigned (.b self)))]))

(implement printable for rgb
  (let to-string (lambda [self : rgb]) -> string
    (format "rgb({}, {}, {})" (r self) (g self) (b self)))))

;; A resource type demonstrating RAII
(let temp-file (type
  :opaque
  [path : string]

  :construct
  (let temp-file-create (lambda [prefix : string]) -> temp-file
    :with (fail io)
    (let [p : string] (io.make-temp-path prefix))
    (io.write-file p "")
    (temp-file p)))

  :viewers
  [(let path (lambda [self : temp-file]) -> string (.path self)))]

  :methods
  [(let write (lambda [self : temp-file] [data : string]) -> unit
     :with (fail io)
     (match (io.write-file (.path self) data)
       [(ok _)  unit]
       [(err e) (raise (format "write failed: {}" e))]))]

  :release
  (lambda [self : temp-file]) -> unit
    :with (io)
    (io.delete-file (.path self)))))    ; cleanup runs automatically at scope exit

;; --- Generic function with constraints + effects ---

(let print-clamped (lambda [val : (& number printable) as T]
                           [lo  : T]
                           [hi  : T]) -> unit
  :with (io log)
  (let [result : T] (clamp val lo hi))
  (log-msg "debug" (format "clamped to {}" (to-string result)))
  (io.println (to-string result))))

;; --- Main ---

(let main (lambda) -> int32
  :with (io)

  ;; Handle the log effect — choose what logging means here
  (handle log in

    (begin
      ;; Concrete, fully typed
      (let [x : int32] 42)
      (let [y : int32 unsigned] 255)

      ;; Default literal types: int64, float64
      (let [big : int64] 1000000)       ; int64 by default
      (let [pi  : float64] 3.14159)     ; float64 by default
      (let [small : int8] 42:int8)      ; explicit narrowing

      ;; Immutable by default — this would be a compile error:
      ;; (set x 43)  ; ERROR: x is not mutable

      ;; Mutable — explicit opt-in
      (let [counter : int64 mut] 0)
      (set counter (+ counter 1))

      ;; Generic dispatch
      (print-clamped x 0:int32 100:int32)
      (print-clamped 3.14 0.0 1.0)

      ;; RAII in action — temp-file is cleaned up at scope exit
      (let [tmp : temp-file] (temp-file-create "work"))
      (write tmp "intermediate results")
      ;; tmp.release called automatically here

      ;; Contiguous array — performance path
      (let [samples : (array float64) mut] (array-new))
      (array-push! samples 1.0)
      (array-push! samples 2.5)
      (array-push! samples 3.7)
      (array-for-each
        (lambda [i : int64] [v : float64]) -> unit
          (io.println (format "sample[{}] = {}" i v)))
        samples)

      ;; Invariant-wrapped type — port-number checks at construction
      (let [port : port-number] (port-number 8080))  ; ok
      ;; (let [bad : port-number] (port-number 99999)) ; compile-time error

      ;; Pattern matching on option
      (let [result : (option int32)] (some 42))
      (match result
        [(some n) (io.println (format "got: {}" n))]
        [(none)   (io.println "nothing")]))

    :on
    [(log-msg level msg)
      (io.eprintln (format "[{}] {}" level msg))]))

  0))
```
