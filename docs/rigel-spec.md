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
   a new name for an existing type, wrap it in a `deftype` with an invariant
   or precondition. This eliminates bare aliases (which are technical debt)
   and nudges users toward encoding semantics. The language auto-generates
   default constructors, viewers, and release when not user-provided, keeping
   the wrapping cost minimal.

8. **Two tiers of data structures.** Persistent immutable collections (`list`,
   `vec`, `map`, `set`) for the functional core. Contiguous mutable containers
   (`array`, `buffer`) for performance-critical paths. The runtime may use C++
   for high-quality implementations of both.

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
(def [x : int32] 42)                         ; signed, checked (safe default)
(def [y : int32 unsigned] 255)               ; unsigned, checked
(def [z : int32 unchecked] 42)               ; signed, wrapping on overflow
(def [w : int32 unsigned unchecked] 255)     ; unsigned, wrapping — "C-style"

(def mut [counter : int64] 0)                        ; mutable, ref-counted (safe default)
(def mut [buf : (array float64 unique)] (array-new)) ; unique owner, no ref-count overhead
(def mut [shared : int64 atomic] 0)                  ; atomic ref-count, thread-safe
```

### 2.3 Constraint-Based Generics

Familiar short names (`int`, `float`, `number`) are **constraints**, not types.
They cannot be used to declare storage directly — only to constrain generic
type parameters.

```scheme
;; CONCRETE: fully specified, allocates exactly 4 bytes
(def (add-saturating [a : int32] [b : int32]) -> int32
  (saturating-add a b))

;; GENERIC: int constraint — works for any signed checked integer
(def (add [a : int] [b : int]) -> int
  (+ a b))

;; GENERIC: number constraint — works for any numeric type
(def (sum [xs : (list number)]) -> number
  (fold + (cast 0 number) xs))
```

### 2.4 Type Labels (Scoped Type Variables)

Within a generic definition, you can **bind a name** to whatever concrete type
the caller provides. This is analogous to C++ template parameters or Haskell's
lowercase type variables, but explicit.

The syntax uses `as` to capture the resolved type:

```scheme
;; T is bound to whatever concrete type matches `int`
(def (add [a : int as T] [b : T]) -> T
  (+ a b))

;; Multiple labels
(def (convert [src : int as S] [dst-type : (type-of float as D)]) -> D
  (cast src D))

;; Label with compound constraint
(def (hash-insert [k : (& hashable eq) as K]
                     [v : any as V]
                     [m : (map K V)]) -> (map K V)
  ...)
```

**Scoping rule:** A type label is visible from its introduction point to the
end of the enclosing form. Labels do not escape their defining scope.

### 2.5 User-Defined Types

Users define new concrete types using `deftype`. Types are **opaque by
default** — fields are not directly accessible from outside. Interaction is
through declared operations only (see §8b for full details).

```scheme
;; A concrete struct type — opaque by default
(deftype point2d
  [x : float64]
  [y : float64]

  :construct
  (def (point [x : float64] [y : float64]) -> point2d
    (point2d x y))

  :viewers
  [(def (x [self : point2d]) -> float64 (.x self))
   (def (y [self : point2d]) -> float64 (.y self))]

  :methods
  [(def (distance [self : point2d] [other : point2d]) -> float64
     (sqrt (+ (pow (- (.x other) (.x self)) 2.0)
              (pow (- (.y other) (.y self)) 2.0))))])

;; An enum / tagged union
(deftype (option T)
  (some [value : T])
  (none))

;; A user-defined numeric type that satisfies `number`
(deftype fixed-point-32
  :opaque
  [raw : int32]
  :satisfies (number)

  :construct
  (def (from-int [n : int32]) -> fixed-point-32
    (fixed-point-32 (* n 256)))    ; 8-bit fractional part

  :viewers
  [(def (to-float [self : fixed-point-32]) -> float64
     (/ (int-to-float (.raw self)) 256.0))]

  :methods
  [(def (add [self : fixed-point-32] [other : fixed-point-32])
       -> fixed-point-32
     (fixed-point-32 (+ (.raw self) (.raw other))))])
```

Users can also define new **constraints** (analogous to type classes/traits):

```scheme
;; Define a constraint
(defconstraint serializable
  (serialize [self : Self]) -> (list int8 unsigned)
  (deserialize [data : (list int8 unsigned)]) -> Self)

;; Declare that a type satisfies it
(implement serializable for point2d
  (def (serialize [self : point2d]) -> (list int8 unsigned)
    ...)
  (def (deserialize [data : (list int8 unsigned)]) -> point2d
    ...))
```

### 2.6 Constraint Composition

Constraints compose via intersection (`&`) and can be used anywhere a single
constraint can:

```scheme
;; K must satisfy both hashable and eq
(def (lookup [k : (& hashable eq) as K]
                [m : (map K any)]) -> (option any)
  ...)

;; Named compound constraint
(defconstraint map-key (& hashable eq comparable))
```

---

## 3. Core Forms

### 3.1 The Unified `def`

Rigel uses a single keyword — `def` — for all bindings: variables, mutations,
and functions. The parser disambiguates structurally:

```scheme
;; Immutable binding: (def [name : type] value)
(def [x : int32] 42)

;; Mutable binding: (def mut [name : type] value)
(def mut [counter : int64] 0)

;; Reassignment of mutable: (def name value)
(def counter (+ counter 1))

;; Multiple bindings (scoped)
(def ([x : int32] 1
      [y : int32] 2)
  (+ x y))

;; Type inference permitted when unambiguous
(def [x] 42)            ; inferred as int64 (default literal type)
(def [x : int32] 42)    ; explicit — preferred style
```

**Disambiguation rules** (the parser checks structurally, no ambiguity in
S-expressions):

| Form | Meaning |
|------|---------|
| `(def [name : type] expr)` | Immutable binding |
| `(def mut [name : type] expr)` | Mutable binding |
| `(def name expr)` | Reassign existing mutable (compile error if immutable) |
| `(def (name params...) -> type body...)` | Named function |
| `(def ([bindings...]) body...)` | Scoped let-block |

### 3.2 Functions

```scheme
;; Named function
(def (add [a : int32] [b : int32]) -> int32
  (+ a b))

;; Generic function with constraint
(def (add [a : number as T] [b : T]) -> T
  (+ a b))

;; Lambda — separate form since it's a value, not a binding
(lambda ([x : int32]) -> int32
  (* x x))

;; Higher-order function
(def (apply-twice [f : (-> T T)] [x : any as T]) -> T
  (f (f x)))
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
(map (lambda ([x : int32]) -> int32 (* x 2)) my-list)
(filter (lambda ([x : int32]) -> bool (> x 0)) my-list)
(fold + 0 my-list)

;; Explicit recursion (tail-call optimized)
(def (factorial [n : int64]) -> int64
  (def (go [acc : int64] [i : int64]) -> int64
    (if (<= i 1)
      acc
      (go (* acc i) (- i 1))))
  (go 1 n))

;; For-each with side effects (returns unit)
(for-each (lambda ([x : int32]) -> unit (print x)) my-list)
```

### 3.5 Data Structures

#### Persistent (Immutable) — The Default

```scheme
;; List (persistent linked list)
(def [xs : (list int32)] '(1 2 3 4))
(def [ys : (list int32)] (cons 0 xs))    ; xs is unchanged

;; Vec (persistent indexed — RRB-tree internally)
(def [v : (vec int32)] [1 2 3 4])
(def [w : (vec int32)] (assoc v 2 99))   ; v is unchanged, w has 99 at index 2

;; Map (persistent — HAMT internally)
(def [m : (map string int32)] {"alice" 1 "bob" 2})
(def [n : (map string int32)] (assoc m "carol" 3))

;; Set (persistent — HAMT internally)
(def [s : (set int32)] #{1 2 3})
```

#### Contiguous (Mutable) — Performance Path

`array` is a flat, contiguous memory region. It is a resource type with RAII
semantics — scope-bound, cache-friendly, and zero-overhead relative to C
arrays. The runtime implementation may use C++ (e.g., bounds-checked
`std::vector` or custom allocators).

```scheme
;; Fixed-size array — stack allocated when size is compile-time known
(def [pixels : (array int8 unsigned 1024)] (array-zero 1024))

;; Dynamic array — heap allocated, growable
(def mut [buf : (array int8 unsigned)] (array-new))
(array-push! buf 42)
(array-push! buf 43)
(def [len : int64] (array-length buf))
(def [val : int8 unsigned] (array-get buf 0))    ; bounds-checked by default

;; Unchecked access for inner loops (explicit opt-in to danger)
(def [val : int8 unsigned] (array-get-unchecked buf 0))

;; Slice — a fat pointer: (ptr, len, shared-ref-to-parent)
;; The shared reference keeps the parent's backing store alive for the slice's lifetime.
(def [window : (slice int8 unsigned)] (array-slice buf 10 20))

;; Array from persistent vec (copies into contiguous memory)
(def [flat : (array int32)] (array-from-vec my-vec))

;; Iterate contiguous memory (cache-friendly)
(array-for-each
  (lambda ([i : int64] [val : int8 unsigned]) -> unit
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
(def mut [out : (buffer)] (buffer-new 4096))
(buffer-write! out b"HTTP/1.1 200 OK\r\n")
(buffer-write! out (serialize response))
(def [data : bytes] (buffer-freeze out))   ; immutable snapshot
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
(deftype port-number
  [value : int16 unsigned]
  :invariant (and (>= value 0) (<= value 65535)))

;; The compiler auto-generates:
;;   - constructor: (port-number 8080) -> port-number
;;       (raises fail if invariant violated)
;;   - viewer: (value pn) -> int16 unsigned
;;   - release: no-op (value type, no resources)

;; Usage
(def [http : port-number] (port-number 80))       ; ok
(def [bad  : port-number] (port-number 70000))     ; compile-time error (literal)
(def [dyn  : port-number] (port-number user-input)) ; runtime check, raises fail

;; Another example: positive integer
(deftype positive-int
  [value : int64]
  :invariant (> value 0))

;; Non-empty string
(deftype non-empty-string
  [value : string]
  :invariant (> (str-length value) 0))

;; Percentage (0.0 to 1.0)
(deftype proportion
  [value : float64]
  :invariant (and (>= value 0.0) (<= value 1.0)))
```

**Why this matters:**

- **No silent semantic confusion.** A `port-number` is not just a `uint16` —
  it has a valid range. The type system enforces this everywhere.
- **Compile-time checking when possible.** If the constructor argument is a
  literal, the compiler checks the invariant statically.
- **Runtime checking otherwise.** Dynamic values are checked at construction
  time, using the `fail` effect for violations.
- **Technical debt becomes visible.** If you find yourself writing
  `(deftype foo [value : int64])` with no invariant, the absence of an
  invariant is a conscious choice, not an oversight.

---

## 4. Module System

```scheme
;; File: math/vector.rgl

(module math.vector
  :exports (vec2 dot cross magnitude normalize))

(deftype vec2
  :opaque
  [x : float64]
  [y : float64]

  :construct
  (def (vec2-new [x : float64] [y : float64]) -> vec2
    (vec2 x y))

  :viewers
  [(def (x [self : vec2]) -> float64 (.x self))
   (def (y [self : vec2]) -> float64 (.y self))])

(def (dot [a : vec2] [b : vec2]) -> float64
  (+ (* (x a) (x b))
     (* (y a) (y b))))
```

```scheme
;; File: main.rgl

(import math.vector :as vec)
(import math.vector :only (dot cross))
(import io)

(def (main) -> int32
  (def [a : vec.vec2] (vec.vec2-new 1.0 2.0))
  (def [b : vec.vec2] (vec.vec2-new 3.0 4.0))
  (io.println (dot a b))
  0)
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
// (def [x : int32] 42) generates:
const int32_t x = 42;

// (def mut [y : int32] 0) generates:
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
(def [name : string] "hello")

;; Byte string — raw bytes
(def [data : bytes] b"raw bytes here")

;; Char — a single Unicode scalar value (not a byte)
(def [c : char] 'λ')

;; String operations return new strings (immutable)
(def [greeting : string] (str-concat "hello, " name))
(def [upper : string] (str-upper name))
(def [len : int64] (str-length name))       ; character count, not byte count
(def [byte-len : int64] (str-byte-length name))
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
(defeffect fail
  (raise [msg : string]) -> never)

(defeffect io
  (read-file [path : string]) -> (result string io-error)
  (write-file [path : string] [data : string]) -> (result unit io-error)
  (println [msg : string]) -> unit)

(defeffect yield
  (yield [value : T]) -> unit)

(defeffect ask
  (ask) -> T)            ; like Reader monad — request a value from context
```

### 8.3 Performing Effects

Functions declare which effects they may perform using `with`:

```scheme
;; This function may fail and do I/O
(def (read-config [path : string]) -> config
  :with (fail io)
  (def [content : string]
    (match (read-file path)
      [(ok s)   s]
      [(err e)  (raise (str-concat "cannot read: " path))]))
  (def [parsed : (result config string)]
    (parse-toml content))
  (match parsed
    [(ok cfg)  cfg]
    [(err msg) (raise msg)]))
```

The `:with` clause is part of the type signature. A function that performs
effects it doesn't declare is a compile error. A function with no `:with`
clause is **pure** — the type system guarantees it.

```scheme
;; Pure function — no effects, compiler enforces this
(def (add [a : int64] [b : int64]) -> int64
  (+ a b))

;; This would be a compile error — println performs io:
;; (def (sneaky [x : int64]) -> int64
;;   (io.println "side effect!")   ; ERROR: performs `io` but not declared
;;   x)
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
(def (process-files [paths : (list string)]) -> unit
  :with (fail io yield)
  (for-each
    (lambda ([p : string]) -> unit
      :with (fail io yield)
      (def [content : string]
        (match (read-file p)
          [(ok s)   s]
          [(err e)  (raise (str-concat "failed: " p))]))
      (yield content))
    paths))

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
(def (try-read-config [path : string]) -> (result config string)
  :with (io)
  (handle fail in
    (ok (read-config path))
    :on [(raise msg) (err msg)]))
```

---

## 8b. Opaque Types, Containment, and RAII

### 8b.1 No Direct Field Access

Types are **opaque by default**. There is no `.field` access syntax for
external code. All interaction with a type's internals goes through explicitly
defined operations:

```scheme
(deftype connection
  :opaque                         ; default, but explicit for clarity
  [handle : int64]
  [state  : (ref connection-state)]
  
  :construct
  (def (connect [host : string] [port : int16 unsigned]) -> connection
    :with (fail io)
    (def [h : int64] (tcp-connect host port))
    (connection h (ref (connected))))

  :methods
  [(def (send [self : connection] [data : bytes]) -> (result int64 io-error)
     :with (io)
     ...)
   (def (is-connected [self : connection]) -> bool
     (match (deref (.state self))    ; .field access only inside methods
       [(connected) true]
       [_           false]))]

  :release
  (def (release [self : connection]) -> unit
    :with (io)
    (tcp-close (.handle self))))
```

**Inside methods:** `.field` access works — the type can see its own guts.

**Outside:** only the operations declared in `:methods` and `:construct` are
visible. The fields `handle` and `state` are completely hidden.

### 8b.2 RAII via `:release`

The `:release` block defines cleanup that runs automatically when a value
goes out of scope, analogous to C++ destructors and Rust's `Drop`:

```scheme
(def (do-work [host : string]) -> unit
  :with (fail io)
  (def [conn : connection] (connect host 8080))
  ;; use conn...
  (send conn b"hello")
  ;; conn.release is called automatically here, even if (send) raised
  )
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

(deftype buffered-connection
  :opaque
  [inner : connection]
  [buffer : (mut-vec int8 unsigned)]

  :construct
  (def (buffered-connect [host : string] [port : int16 unsigned])
      -> buffered-connection
    :with (fail io)
    (buffered-connection (connect host port) (mut-vec-new)))

  :methods
  [(def (send [self : buffered-connection] [data : bytes])
       -> (result int64 io-error)
     :with (io)
     ;; buffer, then flush
     (push-all! (.buffer self) data)
     (when (> (length (.buffer self)) 4096)
       (flush self))
     (ok (byte-length data)))

   (def (flush [self : buffered-connection]) -> (result unit io-error)
     :with (io)
     (def [result : (result int64 io-error)]
       (send (.inner self) (freeze (.buffer self))))
     (clear! (.buffer self))
     (match result
       [(ok _)  (ok unit)]
       [(err e) (err e)]))]

  :release
  (def (release [self : buffered-connection]) -> unit
    :with (io)
    ;; flush remaining, then inner connection cleans up automatically
    (ignore (flush self))))
    ;; (.inner self) release is called automatically (nested RAII)
```

### 8b.4 The Viewer Pattern (Controlled Read Access)

Sometimes you need to expose data without exposing mutability. Rather than
making fields public, define **viewer** functions that return immutable
copies or computed values:

```scheme
(deftype sensor-reading
  :opaque
  [timestamp : int64 unsigned]
  [value     : float64]
  [quality   : int8 unsigned]

  :construct
  (def (reading [ts : int64 unsigned] [val : float64] [q : int8 unsigned])
      -> sensor-reading
    (sensor-reading ts val q))

  :viewers                           ; read-only projections
  [(def (timestamp [self : sensor-reading]) -> int64 unsigned
     (.timestamp self))
   (def (value [self : sensor-reading]) -> float64
     (.value self))
   (def (is-valid [self : sensor-reading]) -> bool
     (> (.quality self) 50))])       ; computed, not raw field
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
(defeffect concurrent
  (spawn [f : (-> T)] ) -> (task T)
  (await [t : (task T)]) -> T
  (await-all [ts : (list (task T))]) -> (list T))
```

A function that spawns work must declare `:with (concurrent)`. A function without
it is guaranteed single-threaded — the compiler enforces this.

### 9.2 Structured Concurrency via Effect Scoping

Effect handlers have lexical scope. A `spawn` effect cannot outlive its handler.
This gives structured concurrency as a language guarantee, not a library
discipline:

```scheme
(handle concurrent in
  (def a (spawn (fetch-users)))
  (def b (spawn (fetch-orders)))
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
(def (main [args : (vec string)]) -> int32
  :with (io concurrent fail)
  (def server (spawn (listen config)))
  (def worker (spawn (process-queue queue)))
  (await-all (list server worker))
  0)
```

On a microcontroller with no OS threads, the `concurrent` handler runs tasks
cooperatively on a single core. On a server, it maps to a work-stealing thread
pool. Same source code, different handler.

### 9.4 Channels — Ownership-Aware Communication

Channels are the primary coordination primitive. The existing ownership system
enforces safety with no additional rules:

```scheme
(def (producer [ch : (channel int32)]) -> unit
  :with (concurrent io)
  (loop [i 0]
    (channel-send ch i)
    (recur (+ i 1))))

(def (consumer [ch : (channel int32)]) -> unit
  :with (concurrent io)
  (loop []
    (def val (channel-recv ch))
    (log "got: {val}")
    (recur)))
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
(def (expensive [x : int64]) -> int64
  (fib x))

;; explicit parallel map — compiler verifies purity of argument function
(def results (par-map data expensive))
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

3. **"One language, two forms."** The theory that compiled and interpreted
   (eval) execution should share the same syntax and semantics — only the
   execution model differs. Not yet fully elaborated in the spec.

---

## 11. Grammar (Preliminary EBNF)

```ebnf
program        = form* ;

form           = def-form | deftype-form | defconstraint-form
               | defeffect-form | implement-form
               | module-form | import-form | expression ;

(* --- The unified `def` --- *)

def-form       = '(' 'def' def-body ')' ;

def-body       = func-def                          (* named function *)
               | 'mut' binding expression           (* mutable binding *)
               | binding expression                  (* immutable binding *)
               | '(' binding+ ')' expression+        (* scoped let-block *)
               | IDENT expression ;                  (* reassignment *)

func-def       = '(' ident param* ')' '->' type-expr effect-clause? expression+ ;

effect-clause  = ':with' '(' IDENT+ ')' ;

param          = '[' ident ':' type-expr label? ']' ;

label          = 'as' IDENT ;

binding        = '[' IDENT ':' type-expr ']'
               | '[' IDENT ']' ;                     (* inferred type *)

(* --- Other definition forms --- *)

deftype-form   = '(' 'deftype' type-def ')' ;
type-def       = IDENT ':opaque'? field* invariant? construct? viewers? methods? release? ;
field          = '[' IDENT ':' type-expr ']' ;
invariant      = ':invariant' expression ;
construct      = ':construct' def-form ;
viewers        = ':viewers' '[' def-form+ ']' ;
methods        = ':methods' '[' def-form+ ']' ;
release        = ':release' def-form ;

defconstraint-form = '(' 'defconstraint' IDENT method-sig+ ')' ;
method-sig     = '(' IDENT param* ')' '->' type-expr ;

defeffect-form = '(' 'defeffect' IDENT method-sig+ ')' ;

implement-form = '(' 'implement' IDENT 'for' IDENT def-form+ ')' ;

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

special-form   = def-form | if-form | match-form | cond-form
               | lambda-form | handle-form | begin-form ;

if-form        = '(' 'if' expression expression expression ')' ;

match-form     = '(' 'match' expression match-clause+ ')' ;
match-clause   = '[' pattern expression ']' ;

pattern        = IDENT | literal | '_'
               | '(' IDENT pattern* ')' ;         (* constructor pattern *)

cond-form      = '(' 'cond' cond-clause+ ')' ;
cond-clause    = '[' expression expression ']'
               | '[' 'else' expression ']' ;

lambda-form    = '(' 'lambda' '(' param* ')' '->' type-expr expression+ ')' ;

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

(defconstraint printable
  (to-string [self : Self]) -> string)

;; --- Effects ---

(defeffect log
  (log-msg [level : string] [msg : string]) -> unit)

;; --- Types (opaque, with RAII) ---

(deftype rgb
  :opaque
  [r : int8 unsigned]
  [g : int8 unsigned]
  [b : int8 unsigned]

  :construct
  (def (rgb-new [r : int8 unsigned]
                   [g : int8 unsigned]
                   [b : int8 unsigned]) -> rgb
    (rgb r g b))

  :viewers
  [(def (r [self : rgb]) -> int8 unsigned (.r self))
   (def (g [self : rgb]) -> int8 unsigned (.g self))
   (def (b [self : rgb]) -> int8 unsigned (.b self))])

(implement printable for rgb
  (def (to-string [self : rgb]) -> string
    (format "rgb({}, {}, {})" (r self) (g self) (b self))))

;; A resource type demonstrating RAII
(deftype temp-file
  :opaque
  [path : string]

  :construct
  (def (temp-file-create [prefix : string]) -> temp-file
    :with (fail io)
    (def [p : string] (io.make-temp-path prefix))
    (io.write-file p "")
    (temp-file p))

  :viewers
  [(def (path [self : temp-file]) -> string (.path self))]

  :methods
  [(def (write [self : temp-file] [data : string]) -> unit
     :with (fail io)
     (match (io.write-file (.path self) data)
       [(ok _)  unit]
       [(err e) (raise (format "write failed: {}" e))]))]

  :release
  (def (release [self : temp-file]) -> unit
    :with (io)
    (io.delete-file (.path self))))    ; cleanup runs automatically at scope exit

;; --- Generic function with constraints + effects ---

(def (print-clamped [val : (& number printable) as T]
                       [lo  : T]
                       [hi  : T]) -> unit
  :with (io log)
  (def [result : T] (clamp val lo hi))
  (log-msg "debug" (format "clamped to {}" (to-string result)))
  (io.println (to-string result)))

;; --- Main ---

(def (main) -> int32
  :with (io)

  ;; Handle the log effect — choose what logging means here
  (handle log in

    (begin
      ;; Concrete, fully typed
      (def [x : int32] 42)
      (def [y : int32 unsigned] 255)

      ;; Default literal types: int64, float64
      (def [big : int64] 1000000)       ; int64 by default
      (def [pi  : float64] 3.14159)     ; float64 by default
      (def [small : int8] 42:int8)      ; explicit narrowing

      ;; Immutable by default — this would be a compile error:
      ;; (def x 43)

      ;; Mutable — explicit opt-in
      (def mut [counter : int64] 0)
      (def counter (+ counter 1))

      ;; Generic dispatch
      (print-clamped x 0:int32 100:int32)
      (print-clamped 3.14 0.0 1.0)

      ;; RAII in action — temp-file is cleaned up at scope exit
      (def [tmp : temp-file] (temp-file-create "work"))
      (write tmp "intermediate results")
      ;; tmp.release called automatically here

      ;; Contiguous array — performance path
      (def mut [samples : (array float64)] (array-new))
      (array-push! samples 1.0)
      (array-push! samples 2.5)
      (array-push! samples 3.7)
      (array-for-each
        (lambda ([i : int64] [v : float64]) -> unit
          (io.println (format "sample[{}] = {}" i v)))
        samples)

      ;; Invariant-wrapped type — port-number checks at construction
      (def [port : port-number] (port-number 8080))  ; ok
      ;; (def [bad : port-number] (port-number 99999)) ; compile-time error

      ;; Pattern matching on option
      (def [result : (option int32)] (some 42))
      (match result
        [(some n) (io.println (format "got: {}" n))]
        [(none)   (io.println "nothing")]))

    :on
    [(log-msg level msg)
      (io.eprintln (format "[{}] {}" level msg))]))

  0)
```
