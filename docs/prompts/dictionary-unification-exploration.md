# Rigel Dictionary Unification Exploration

You are helping design a fundamental rethinking of Rigel's data model. Rigel is a strongly-typed,
immutable-by-default, Scheme-derived language. The full language specification is in
`docs/rigel-spec.md`. Read it before proceeding.

## Core Thesis

Rigel has historically been built on lists (S-expressions, inherited from Scheme). This exploration
proposes that **the dictionary — not the list — is Rigel's fundamental composite structure**. The
language reduces to two primitives:

- **Atoms**: irreducible values (`42`, `3.14`, `true`, `"hello"`)
- **Dictionaries**: named collections of entries, where entries may be atoms, other dictionaries,
  or callables

Everything else — functions, closures, types, modules, scopes — is a dictionary satisfying
particular constraints, with syntactic sugar for common shapes.

## What Was Unified

Traditional Rigel has separate concepts for functions, closures, types, and modules. Under dictionary
unification, these collapse:

| Traditional concept | Under unification |
|---------------------|-------------------|
| Function            | A dictionary satisfying `callable` (has `:args`, `:returns`, `:body`; no captures) |
| Closure             | A callable dictionary that also has captured entries |
| Type instance       | A dictionary with data entries and method entries |
| Type definition     | A dictionary schema with constraints, opacity, and lifecycle |
| Module              | A dictionary of dictionaries |
| Scope               | A dictionary of bindings |

A closure is data (captures) + code (body). A type instance is data (fields) + code (methods).
These are the same construct: a dictionary of named entries, some of which are values and some of
which are callable.

## What Distinguishes Dictionary Kinds

The difference between a plain dictionary and a type is not structural — it's the constraints
applied:

| Property             | Plain dict | Type        | Callable    |
|----------------------|------------|-------------|-------------|
| Keys constrained     | no         | yes (schema)| yes (:args, :returns, :body) |
| Opaque               | no         | by default  | n/a         |
| Lifecycle (:release) | no         | optional    | no          |
| Satisfies constraints| optional   | yes         | yes         |

A type is a *constrained, opaque dictionary with lifecycle*. A callable is a *dictionary with
argument schema and a body*. A plain dictionary is unconstrained.

## Design Dimensions

Explore whichever dimension the user specifies:

### Dimension 1: Naming Without `let`

The current spec uses `let` as a special form for binding names. Under dictionary unification,
naming is just a `:name` entry in the dictionary:

```scheme
;; Current: special form
(let add (lambda (:args [a : int32] [b : int32]) (:returns int32) (+ a b)))

;; Proposed: :name is a dictionary entry
(lambda :name add
  :args (dict :a int32 :b int32)
  :returns int32
  (+ a b))

;; Anonymous — just omit :name
(lambda :args (dict :x int32) :returns int32 (* x x))
```

Questions to explore:
- What replaces scoped `let` blocks? Is a scope just an anonymous dictionary?
- How does `set` (mutation) work on dictionary entries?
- Does `:name` vs `:label` matter? (`:name` suggests identity; `:label` suggests reference)
- How does this interact with the module system (currently a dictionary of exports)?

### Dimension 2: Types as Constrained Dictionaries

Types are currently defined with a `type` special form containing fields and keyword sections.
Under unification, a type IS a dictionary schema:

```scheme
;; Current syntax
(let point2d (type
  [x : float64]
  [y : float64]
  :construct (let point ...)
  :viewers [...]
  :methods [...]
  :release ...))

;; Proposed: type is sugar for a constrained dictionary schema
(type :name point2d
  :schema (dict :x float64 :y float64)
  :construct (lambda :args (dict :x float64 :y float64) :returns point2d
    (point2d (dict :x x :y y)))
  :viewers (dict
    :x (lambda :args (dict :self point2d) :returns float64 (.x self))
    :y (lambda :args (dict :self point2d) :returns float64 (.y self)))
  :methods (dict
    :distance (lambda :args (dict :self point2d :other point2d) :returns float64
      (sqrt (+ (pow (- (.x other) (.x self)) 2.0)
               (pow (- (.y other) (.y self)) 2.0))))))
```

Questions to explore:
- What happens to enum/tagged union types under this model?
- How do invariants/preconditions attach to a dictionary schema?
- Can a type schema be composed from other schemas (dictionary merging)?
- How do `:satisfies` constraints work when the type IS a dictionary?

### Dimension 3: Named Arguments and Calling Conventions

If function arguments are a dictionary, calling becomes dictionary construction:

```scheme
;; Positional (legacy or sugar)
(distance p1 p2)

;; Named — constructing the args dictionary
(distance :self p1 :other p2)

;; Partial application = partial dictionary
(distance :self origin)  ;; returns a callable wanting :other
```

Questions to explore:
- Is positional calling still supported (as sugar), or exclusively named?
- How does partial application via partial dictionaries interact with currying?
- What are the implications for generic programming and constraint satisfaction?
- How does this affect error messages (missing key vs. wrong argument position)?

### Dimension 4: Serialization and JSON Interchangeability

If type instances are dictionaries, serialization to JSON (and back) becomes nearly trivial:

```scheme
;; A point2d instance IS this dictionary:
(dict :x 3.0 :y 4.0)

;; JSON representation:
;; {"_type": "point2d", "x": 3.0, "y": 4.0}
```

Questions to explore:
- What is the canonical serialization format? Is `_type` the right tag, or something else?
- How do opaque types serialize? Do they refuse, or use a declared serialization projection?
- How do callable entries serialize (or not)?
- What about cyclic references?
- How does this interact with the `serializable` constraint?

### Dimension 5: Dataflow Execution Model

This is the most far-reaching implication. If callables are dictionaries with named inputs, the
compiler can build a dependency DAG from argument references. Execution ordering is constrained
only by data dependencies — everything else is free:

```scheme
;; No data dependencies between a, b, c — can execute in any order or in parallel
(dict :name a :body (compute-x sensor1))
(dict :name b :body (compute-y sensor2))
(dict :name c :body (compute-z sensor3))

;; This depends on a, b, c — must wait for all three
(dict :name result :body (combine a b c))
```

Questions to explore:
- How explicit should the dataflow model be? Compiler-discovered vs. programmer-annotated?
- What are the implications for Rigel's existing effect system? Effects impose ordering.
- How does mutable state (`:mut`) interact with dataflow scheduling?
- Can the compiler provide a "parallelism report" showing the discovered DAG?
- What is the relationship to existing dataflow languages (Id, Sisal, Val)?
- How does this interact with the concurrency model (channels, tasks)?

### Dimension 6: The Neuron Analogy and Computational Model

A Rigel callable structurally resembles a neuron: receives named inputs (dendrites/args), has
internal state (soma/captures+fields), produces output (axon/return), fires when inputs are
satisfied. A network of callables resembles a neural network — but with explicit ordering
constraints from argument dependencies.

The degrees of freedom in execution ordering have implications for:
- **Code migration**: self-describing dictionaries can move between execution contexts
- **Scheduling**: the runtime can reorder within dependency constraints
- **Parallel processing**: independent callables execute concurrently by default
- **Synchronization**: only required where data dependencies exist

Questions to explore:
- Is this analogy useful for language design, or just for explanation?
- Could Rigel's execution model be formally defined in terms of dataflow graphs?
- What would a "network topology" view of a Rigel program look like?
- How does back-pressure and flow control map to this model?
- Are there optimization opportunities the compiler can exploit from this framing?

### Dimension 7: Syntax — S-expressions vs. Alternatives

The current spec uses S-expressions. Dictionary unification raises the question of whether `{}`
should denote dictionaries, or whether keyword-prefixed S-expressions are sufficient:

```scheme
;; Option A: S-expressions with keyword prefix (recommended for LLM generation)
(dict :x 3.0 :y 4.0)

;; Option B: Curly braces
{:x 3.0 :y 4.0}

;; Option C: Clojure-style maps
{:x 3.0, :y 4.0}
```

LLM perspective: S-expressions are easier to generate correctly — fewer token types, unambiguous
nesting, no bracket-matching across multiple delimiter types. But `{}` provides a strong visual
signal for "this is a dictionary."

Questions to explore:
- Does the dictionary-everywhere model make `{}` more valuable (visual distinction)?
- Or does "everything is a dictionary" mean there's nothing to distinguish FROM?
- What does Clojure's experience with mixed `()` `[]` `{}` tell us?
- How does syntax choice affect tooling (paredit, rainbow parens, indentation)?

## Ground Rules for Exploration

- Read the current spec (`docs/rigel-spec.md`) before proposing changes. Understand what exists.
- This is exploration, not specification. Sketch freely, identify tradeoffs, note open questions.
- Refer to relevant PL theory and existing languages (Clojure, Smalltalk, Self, dataflow
  languages) but don't blindly copy. Rigel's effect system and immutability defaults create
  different constraints.
- Keep syntax Scheme-flavored unless there's a strong reason to deviate.
- The primary consumer of Rigel syntax is an LLM generating code. Optimize for correctness of
  generation, not human typing speed.
- Think about compilation to C — dictionaries must have efficient runtime representations.
  A dictionary with a known schema at compile time can be a C struct. Dynamic dictionaries
  need a different strategy.
- Connect ideas to the existing spec. Note which spec sections would need revision if a
  dimension is adopted.
