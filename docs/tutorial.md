# Learn Rigel in One Sitting

A tutorial for programmers who know at least one language and want to read and
write Rigel fluently. No prior Scheme or Lisp experience required.

---

## 1. Everything Is an Expression Inside Parentheses

Rigel uses **S-expressions** — every operation is written as `(operator arguments...)`.
If you've used Lisp or Scheme, this is home. If not, here's the one rule:

```scheme
(+ 1 2)          ; => 3
(* 3 (+ 1 2))    ; => 9  — nesting works naturally
(> 5 3)           ; => true
```

There are no operator precedence rules to memorize. The parentheses *are* the
precedence. `(* 3 (+ 1 2))` is unambiguous — add first, then multiply.

**Comments** start with `;` and run to end of line.

---

## 2. Bindings: Naming Things

Use `let` with square brackets to create a named value:

```scheme
(let [x : int32] 42)
(let [name : string] "hello")
(let [pi : float64] 3.14159)
```

The pattern is: `(let [name : type] value)`.

Every binding is **immutable by default**. Once you set `x` to 42, it stays 42.
This isn't a limitation — it's the point. Most values in most programs never
change.

### What are `int32` and `float64`?

Rigel uses explicit type names that say exactly what they are:

| Type | What it is |
|------|-----------|
| `int8`, `int16`, `int32`, `int64` | Signed integers of that many bits |
| `float32`, `float64` | IEEE floating-point numbers |
| `bool` | `true` or `false` |
| `string` | UTF-8 text |
| `char` | A single Unicode character |

There is no bare `int` type. If you want a 32-bit integer, you say `int32`.
(We'll see what `int` *actually* means later — it's more interesting than a type.)

### Literal Defaults

If you don't annotate a number, Rigel picks a sensible default:

```scheme
(let [x] 42)       ; type inferred as int64 (the default for integer literals)
(let [y] 3.14)     ; type inferred as float64 (the default for float literals)
```

You can narrow with a suffix:

```scheme
(let [small : int8] 42:int8)
(let [precise : float32] 3.14:float32)
```

---

## 3. Mutable Bindings

When you genuinely need a value that changes, say so explicitly with `mut`
inside the binding brackets:

```scheme
(let [counter : int64 mut] 0)
```

Now you can reassign it using `set`:

```scheme
(set counter (+ counter 1))    ; counter is now 1
(set counter (+ counter 1))    ; counter is now 2
```

If you try to reassign an immutable binding, the compiler stops you:

```scheme
(let [x : int32] 42)
(set x 43)                     ; COMPILE ERROR: x is immutable
```

---

## 4. Functions

Functions are lambdas bound to a name with `let`. The `lambda` keyword
introduces the function value:

```scheme
(let add (lambda (:args [a : int32] [b : int32]) (:returns int32)
  (+ a b))
```

Read it as: *bind `add` to a lambda that takes two `int32` parameters
and returns an `int32`.*

Call it like any other operation:

```scheme
(add 3 4)    ; => 7
```

### Multi-expression Bodies

The last expression in a function body is the return value. You can have
multiple expressions — useful for sequential operations:

```scheme
(let greet (lambda (:args [name : string]) (:returns string)
  (let [greeting : string] (str-concat "Hello, " name))
  (str-concat greeting "!")))

(greet "world")    ; => "Hello, world!"
```

### Anonymous Functions (Lambdas)

When you need a function as a value (to pass to another function), use `lambda`
without binding it to a name:

```scheme
(lambda (:args [x : int32]) (:returns int32) (* x x))
```

This creates a function that squares its input. Lambdas are values — you can
pass them around:

```scheme
(map (lambda (:args [x : int32]) (:returns int32) (* x x))
     '(1 2 3 4))
; => (1 4 9 16)
```

### Closures and Captures

A lambda can capture bindings from its environment, but it must declare them
explicitly using `:capture`:

```scheme
(let [total : int64 mut] 0)
(let accumulate (lambda (:capture [total mut]) (:args [value : int64]) (:returns int64)
  (set total (+ total value))
  total))

(accumulate 10)    ; => 10
(accumulate 20)    ; => 30
```

Captures without a type annotation close over an existing binding. The `mut`
qualifier allows mutation of the captured state.

---

## 5. Control Flow

### If

`if` is an expression — it always produces a value:

```scheme
(if (> x 0)
  "positive"
  "non-positive")
```

Both branches are required. There's no "if without else" because every
expression must produce a value.

### Pattern Matching

`match` is how you branch on the shape of data:

```scheme
(match x
  [0 "zero"]
  [1 "one"]
  [_ "other"])     ; _ matches anything
```

This becomes much more powerful with custom types (§9). For now, think of it
as a `switch` that can also destructure data.

### Multi-Way Conditionals

`cond` is like a chain of if/else-if:

```scheme
(cond
  [(< x 0) "negative"]
  [(= x 0) "zero"]
  [else     "positive"])
```

---

## 6. Collections

Rigel has two families of collections: **persistent** (immutable, the default)
and **contiguous** (mutable, for performance).

### Persistent Collections (Immutable)

These never change in place. "Modifying" one creates a new version; the
original is untouched.

```scheme
;; List — linked list
(let [xs : (list int32)] '(1 2 3 4))
(let [ys : (list int32)] (cons 0 xs))    ; ys is (0 1 2 3 4), xs unchanged

;; Vec — indexed collection (like an array you can't mutate)
(let [v : (vec int32)] [1 2 3 4])
(let [w : (vec int32)] (assoc v 2 99))   ; w is [1 2 99 4], v unchanged

;; Map — key-value pairs
(let [m : (map string int32)] {"alice" 1 "bob" 2})
(let [n : (map string int32)] (assoc m "carol" 3))

;; Set — unique values
(let [s : (set int32)] #{1 2 3})
```

Notice: types of collections are written `(list int32)`, `(map string int32)`,
etc. The container name comes first, then the element type(s).

### Collection Processing

No `for` loops. Instead, use `map`, `filter`, and `fold`:

```scheme
;; Double every element
(map (lambda (:args [x : int32]) (:returns int32) (* x 2)) '(1 2 3))
; => (2 4 6)

;; Keep only positives
(filter (lambda (:args [x : int32]) (:returns bool) (> x 0)) '(-1 2 -3 4))
; => (2 4)

;; Sum a list
(fold + 0 '(1 2 3 4))
; => 10
```

If you know JavaScript's `.map()`, `.filter()`, `.reduce()` — same idea,
different syntax.

### Contiguous Collections (Mutable)

When you need raw performance (tight loops, cache-friendly memory), use `array`:

```scheme
(let [buf : (array float64) mut] (array-new))
(array-push! buf 1.0)
(array-push! buf 2.5)
(array-push! buf 3.7)
(let [val : float64] (array-get buf 0))    ; 1.0 — bounds-checked
```

The `!` suffix on `array-push!` is a convention (not enforced by the language)
indicating "this mutates something."

Arrays are bounds-checked by default. If you need unchecked access in a hot
loop, you opt in explicitly: `(array-get-unchecked buf 0)`.

---

## 7. Recursion Instead of Loops

Rigel has no `for` or `while`. Instead, you write recursive functions. The
compiler turns tail recursion into loops automatically, so there's no
performance penalty:

```scheme
(let factorial (lambda (:args [n : int64]) (:returns int64)
  (let go (lambda (:args [acc : int64] [i : int64]) (:returns int64)
    (if (<= i 1)
      acc
      (go (* acc i) (- i 1))))
  (go 1 n)))
```

`go` calls itself as the very last thing it does (tail position), so the
compiler compiles this into a `while` loop in the generated code. No stack
overflow, no matter how large `n` is.

In practice, you'll use `map`, `filter`, and `fold` far more often than
explicit recursion.

---

## 8. Safe by Default, Dangerous by Choice

Rigel's defaults are always the safe choice. You opt into danger explicitly
using **qualifiers**:

```scheme
(let [x : int32] 42)                          ; signed, checked (safe)
(let [y : int32 unsigned] 255)                 ; unsigned, still checked
(let [z : int32 unchecked] 42)                 ; signed, wraps on overflow
(let [w : int32 unsigned unchecked] 255)       ; unsigned, wrapping — "C-style"
```

**Checked** means overflow traps at runtime (or compile time if detectable).
**Unchecked** means overflow wraps silently, like C. You have to ask for the
dangerous behavior.

This pattern — safe default, explicit opt-in — repeats throughout the language:
- Immutable by default → `mut` to opt in
- Bounds-checked arrays → `array-get-unchecked` to opt in
- Signed arithmetic → `unsigned` to opt in
- Overflow-checking → `unchecked` to opt in

---

## 9. Defining Your Own Types

### Structs

Use `type` inside a `let` binding to define a new type. Types are **opaque by
default** — code outside the type can't peek at the fields:

```scheme
(let point2d (type
  [x : float64]
  [y : float64]

  :construct
  (let point (lambda (:args [x : float64] [y : float64]) (:returns point2d)
    (point2d x y))

  :viewers
  [(let x (lambda (:args [self : point2d]) (:returns float64) (.x self)))
   (let y (lambda (:args [self : point2d]) (:returns float64) (.y self)))]

  :methods
  [(let distance (lambda (:args [self : point2d] [other : point2d]) (:returns float64)
     (sqrt (+ (pow (- (.x other) (.x self)) 2.0)
              (pow (- (.y other) (.y self)) 2.0))))]))
```

Let's unpack this:

- **Fields** (`[x : float64]`) are internal — only visible inside the type's
  own code via `.x`, `.y` syntax.
- **`:construct`** defines how to create a `point2d`. Users call `(point 1.0 2.0)`.
- **`:viewers`** define read-only accessors. Outside code calls `(x my-point)`
  and `(y my-point)`.
- **`:methods`** define operations. Call `(distance p1 p2)`.

Usage:

```scheme
(let [p1 : point2d] (point 1.0 2.0))
(let [p2 : point2d] (point 4.0 6.0))
(x p1)              ; => 1.0
(distance p1 p2)    ; => 5.0
```

### Enums (Tagged Unions)

```scheme
(let option (type [T]
  (some [value : T])
  (none)))
```

Use `match` to branch on variants:

```scheme
(let [result : (option int32)] (some 42))

(match result
  [(some n) (+ n 1)]    ; => 43
  [(none)   0])
```

### Types With Invariants

Rigel has no type aliases. If you want to name a type, you must wrap it — and
the language nudges you toward adding an invariant that justifies the name:

```scheme
(let port-number (type
  [value : int16 unsigned]
  :invariant (and (>= value 0) (<= value 65535))))
```

Now `(port-number 80)` succeeds, but `(port-number 70000)` is a compile-time
error (if the argument is a literal) or a runtime error (if dynamic). The
compiler auto-generates the constructor and a viewer — you don't need to write
them yourself.

```scheme
(let [http : port-number] (port-number 80))       ; ok
(let [bad  : port-number] (port-number 70000))     ; compile-time error
```

---

## 10. Generics: What `int` and `number` Actually Mean

Remember how we said there's no bare `int` type? Here's the payoff: `int`,
`float`, and `number` are **constraints** — they describe *families* of types
rather than specific types.

```scheme
;; This is CONCRETE — only works with int32
(let add-i32 (lambda (:args [a : int32] [b : int32]) (:returns int32)
  (+ a b))

;; This is GENERIC — works with any signed checked integer
(let add (lambda (:args [a : int] [b : int]) (:returns int)
  (+ a b))
```

The generic `add` works with `int8`, `int16`, `int32`, or `int64`. The compiler
generates a specialized version for each type actually used — no runtime
overhead.

The constraint hierarchy:

```
number
├── int        (any signed checked integer)
├── float      (any IEEE float)
└── ...
```

### Type Labels

Sometimes you need to say "these two parameters must be the *same* type." Use
`as` to capture the resolved type:

```scheme
(let add (lambda (:args [a : int as T] [b : T]) (:returns T)
  (+ a b))
```

Now `(add 1:int32 2:int32)` works, but `(add 1:int32 2:int64)` is a type
error — `T` was bound to `int32` by the first argument.

### Constraint Composition

Combine constraints with `&`:

```scheme
(let lookup (lambda (:args [k : (& hashable eq)] [m : (map k any)]) (:returns (option any))
  ...))
```

`k` must satisfy both `hashable` and `eq`.

---

## 11. Effects: Declaring What a Function *Does*

Here's a question most languages ignore: *can you tell, just from a function's
signature, whether it reads files, writes to the network, or might fail?*

In Rigel, you can. Every side effect is **declared** in the function signature:

```scheme
;; Pure function — no effects
(let add (lambda (:args [a : int64] [b : int64]) (:returns int64)
  (+ a b))

;; This function may fail and do I/O
(let read-config (lambda (:args [path : string]) (:returns config) (:with (fail io))
  ...))
```

The `:with (fail io)` clause says: this function may raise errors (`fail`) and
perform I/O (`io`). A function with no `:with` clause is **guaranteed pure** by
the compiler.

### Performing Effects

Inside an effectful function, you use the effect's operations:

```scheme
(let read-config (lambda (:args [path : string]) (:returns config) (:with (fail io))
  (let [content : string]
    (match (read-file path)                      ; read-file is an io operation
      [(ok s)   s]
      [(err e)  (raise (str-concat "cannot read: " path))]))  ; raise is a fail operation
  (parse content)))
```

### Handling Effects

The caller decides *what effects actually do* using `handle`:

```scheme
;; In production — real file I/O
(handle io in
  (read-config "/etc/app.toml")
  :on
  [(read-file p)    (os.read-file p)]
  [(write-file p d) (os.write-file p d)]
  [(println msg)    (os.stdout.write-line msg)])

;; In tests — mock everything
(handle io in
  (read-config "/etc/app.toml")
  :on
  [(read-file p)    (ok "[database]\nhost = \"localhost\"")]
  [(write-file p d) (ok unit)]
  [(println msg)    unit])
```

Same function, same code path, completely different behavior. No dependency
injection framework, no mock library — just a different handler.

### Converting Effects to Values

You can catch a `fail` effect and turn it into a `result` value:

```scheme
(handle fail in
  (ok (read-config path))
  :on
  [(raise msg) (err msg)])
; returns: (result config string)
```

### Why This Matters

When reading code, `:with (fail io)` tells you at a glance exactly what kind
of side effects to expect. When writing code, the compiler forces you to be
honest — try to sneak in an `io` operation without declaring it, and the
compiler rejects it.

---

## 12. Modules

Code is organized into modules. Each file declares its module and what it
exports:

```scheme
;; File: math/vector.rgl
(module math.vector
  :exports (vec2 dot cross magnitude))

(let vec2 (type ...))

(let dot (lambda (:args [a : vec2] [b : vec2]) (:returns float64)
  ...))
```

Import from other modules:

```scheme
(import math.vector :as vec)       ; qualified: vec.dot, vec.vec2
(import math.vector :only (dot))   ; unqualified: just dot
(import io)                        ; everything from io
```

---

## 13. Resource Cleanup (RAII)

Some types own resources — file handles, network connections, temporary files.
Rigel cleans these up automatically when they go out of scope, using `:release`:

```scheme
(let temp-file (type
  :opaque
  [path : string]

  :construct
  (let temp-file-create (lambda (:args [prefix : string]) (:returns temp-file) (:with (fail io))
    (let [p : string] (io.make-temp-path prefix))
    (io.write-file p "")
    (temp-file p)))

  :release
  (lambda (:args [self : temp-file]) (:returns unit) (:with (io))
    (io.delete-file (.path self)))))
```

Usage:

```scheme
(let do-work (lambda (:returns unit) (:with (fail io))
  (let [tmp : temp-file] (temp-file-create "work"))
  (write tmp "data")
  ;; tmp is automatically cleaned up here — even if (write) raised an error
  ))
```

If you know C++ (RAII/destructors) or Rust (`Drop`) or Python (`with`
statements), this is the same idea — but automatic and scope-based with no
special syntax at the call site.

---

## 14. Concurrency

Spawning concurrent work is an effect, like everything else:

```scheme
(let main (lambda (:args [args : (vec string)]) (:returns int32) (:with (io concurrent fail))

  (handle concurrent in
    (let [users  : (task (list user))]  (spawn (fetch-users)))
    (let [orders : (task (list order))] (spawn (fetch-orders)))
    (merge-results (await users) (await orders))
    :on
    [(spawn f)   (schedule-on-pool f)]
    [(await t)   (block-until-complete t)]
    [(await-all ts) (block-until-all-complete ts)])

  0))
```

Key ideas:
- `spawn` creates a concurrent task. `await` waits for its result.
- All spawned tasks **must complete before the handler scope ends**. No orphan
  threads, no fire-and-forget. The compiler enforces this.
- Tasks communicate through **channels**:

```scheme
(let producer (lambda (:args [ch : (channel int32)]) (:returns unit) (:with (concurrent))
  (channel-send ch 42)))

(let consumer (lambda (:args [ch : (channel int32)]) (:returns unit) (:with (concurrent io))
  (let [val] (channel-recv ch))
  (io.println (format "got: {}" val))))
```

### Pure Parallelism

If a function is pure (no `:with` clause), the compiler knows it's safe to
run in parallel:

```scheme
(let expensive (lambda (:args [x : int64]) (:returns int64)
  (fib x)))

(let results (par-map data expensive))    ; safe — compiler verified purity
```

---

## 15. Putting It All Together

Here's a small but complete program that uses most of what we've covered:

```scheme
(module main :exports (main))

(import io)

;; A type with an invariant
(let percentage (type
  [value : float64]
  :invariant (and (>= value 0.0) (<= value 100.0))))

;; A type for exam scores
(let exam-result (type
  :opaque
  [student : string]
  [score   : percentage]

  :construct
  (let exam-result-new (lambda (:args [student : string] [score : float64]) (:returns exam-result) (:with (fail))
    (exam-result student (percentage score))))

  :viewers
  [(let student (lambda (:args [self : exam-result]) (:returns string) (.student self)))
   (let score   (lambda (:args [self : exam-result]) (:returns percentage) (.score self)))]))

;; Pure function — works on any list of exam-result
(let average-score (lambda (:args [results : (list exam-result)]) (:returns float64)
  (let [total : float64]
    (fold (lambda (:args [acc : float64] [r : exam-result]) (:returns float64)
            (+ acc (value (score r))))
          0.0
          results))
  (/ total (int-to-float (length results)))))

;; Effectful — reads from I/O, may fail
(let load-results (lambda (:args [path : string]) (:returns (list exam-result)) (:with (fail io))
  (let [content : string]
    (match (read-file path)
      [(ok s)   s]
      [(err e)  (raise "cannot read results file")]))
  (parse-exam-results content)))

;; Entry point
(let main (lambda (:returns int32) (:with (io))
  (handle fail in
    (handle io in
      (do
        (let [results : (list exam-result)]
          (load-results "scores.csv"))
        (let [avg : float64] (average-score results))
        (io.println (format "Average: {}%" avg))
        0)
      :on
      [(read-file p)    (os.read-file p)]
      [(write-file p d) (os.write-file p d)]
      [(println msg)    (os.stdout.write-line msg)])
    :on
    [(raise msg)
      (do
        (io.eprintln (format "Error: {}" msg))
        1)])))
```

---

## Quick Reference Card

| Concept | Syntax |
|---------|--------|
| Immutable binding | `(let [x : int32] 42)` |
| Mutable binding | `(let [x : int32 mut] 0)` |
| Reassignment | `(set x (+ x 1))` |
| Named function | `(let name (lambda (:args [a : T] [b : T]) (:returns T) body)` |
| Anonymous lambda | `(lambda (:args [x : T]) (:returns T) body)` |
| Closure w/ capture | `(lambda (:capture [x mut]) (:args [a : T]) (:returns T) body)` |
| If | `(if cond then else)` |
| Match | `(match val [pattern expr] ...)` |
| Cond | `(cond [test expr] ... [else expr])` |
| List literal | `'(1 2 3)` |
| Vec literal | `[1 2 3]` |
| Map literal | `{"k" v ...}` |
| Set literal | `#{1 2 3}` |
| Generic constraint | `[a : int]`, `[a : number]` |
| Type label | `[a : int as T]` |
| Effect declaration | `:with (fail io)` |
| Effect handling | `(handle eff in body :on [clauses])` |
| Opaque type | `(let name (type :opaque fields ...))` |
| Invariant type | `(let name (type [v : T] :invariant expr))` |
| Module | `(module name :exports (syms))` |
| Import | `(import mod :as alias)` |

---

## Where Next

- Read the full specification: `docs/rigel-spec.md`
- The **effects system** (§8 in the spec) has more depth — resumable effects,
  effect composition, and how effects compile to C
- The **memory model** (§5) covers ownership qualifiers (`unique`, `atomic`)
  and how the compiler prevents data races
- The **concurrency model** (§9) shows how structured concurrency emerges from
  the effect system
