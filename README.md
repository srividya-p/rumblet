# rumblet

A local Python toy query engine. Behavior is defined exclusively by
`mini-data-model.html` and `mini-query-language.html`.

## Slices 00–04: foundations

The notes below describe behavior at the end of each slice. Query fixtures
track the current CLI behavior.

### Slice 00: initialization

The package, CLI scaffold, and tests exist. Query evaluation is not implemented.
Every `run --expr` invocation currently prints an initialization diagnostic to
stderr and exits with code 2. This is scaffold behavior, not query semantics.

The intended architecture is parse -> AST -> runtime iterators
(`open` / `next` / `close` / `reset`) -> print a sequence.
File input and language features will be added in later slices.
The specs leave output formatting unspecified; that choice is deferred until
the first evaluation slice.

Use the existing uv-managed environment; no dependencies are required:

```bash
source .venv/bin/activate
python -m rumblet --help
python -m unittest discover -s tests -v
python -m rumblet run --expr '1'
python -m rumblet run --expr 'true'
python -m rumblet run --expr '()'
```

Each example prints `rumblet: query evaluation is not implemented yet` to stderr
with no stdout and exit code 2. The same queries live in
`tests/queries/slice00/cases.json`, consumed directly by the unit tests.

### Slice 01: atomic values

`rumblet.values` implements immutable `StringValue`, `NumberValue`,
`BooleanValue`, and `NullValue` (also available as `NULL`). Equality compares
kind and content; separately constructed nulls represent the same model value.
Strings reject surrogate code points and count Unicode scalar values with `len`.
No Unicode normalization is performed.

All atomic `.value` payloads are compatible with Python's standard JSON encoder
and decoder: strings, integers or finite floats, booleans, and `None` for null.
Integers and floats share the JSON kind `number`; booleans remain a distinct kind.
Numeric precision is unspecified by the spec; fractional numbers use Python's
float precision. NaN and infinities are rejected. Model values reject implicit
Python truth conversion; query effective
boolean values will be implemented separately.

This slice adds no parser or evaluation behavior. The query examples in
`tests/queries/slice01/cases.json` test the current CLI diagnostic, while
`tests/test_slice01.py` tests the atomic model directly.

### Slice 02: containers, nesting, and identity

`ArrayValue` accepts a list of model values. `ObjectValue` accepts a dictionary
of string names to model values, or a list of name/value pairs to detect duplicate
names. Duplicate names raise `ValueError`; invalid names or contents are rejected.
Both containers accept all six model kinds, including nested arrays and objects.
Raw Python values and query sequences cannot be used as container elements.

Arrays compare by position and length. Objects compare by names and corresponding
values, ignoring member order. All six kinds compare and hash by kind and content;
Python object identity has no model significance. Immutable internal storage
prevents aliases from changing a value. Container `.value` properties return fresh
JSON-compatible lists/dictionaries. Internal tuples and frozensets are storage
details, not additional model kinds. No explicit nesting limit is added; Python's
normal recursion and memory limits apply.

Tests and matching query examples are in `tests/test_slice02.py` and
`tests/queries/slice02/cases.json`. The examples also include model contents for
direct model tests. Query evaluation remains unimplemented; CLI examples continue
to report the scaffold diagnostic with exit code 2.

### Slice 03: sequences, printing, and errors

`Sequence([value, ...])` is a list-backed query sequence, separate from `Value`.
It preserves order and duplicates, accepts only model values, and cannot occur
inside an array, object, or another sequence. Its `.values` property returns a
copy of the list. `print_sequence(sequence, file=...)` prints one compact JSON
value per line, or `()` followed by a newline for an empty sequence. Object keys
are sorted for reproducible output; strings retain JSON quotes and escapes.
This output convention is an implementation choice because the specs do not
define serialization. Empty arrays and null print as `[]` and `null` respectively.

`StaticError` and `DynamicError` in `rumblet.errors` distinguish static query
failures from invalid runtime operations. The CLI handles both and prints engine
sequences, but query evaluation itself is still unimplemented.

`tests/queries/slice03/cases.json` records the matching query expressions,
printer outputs, and current CLI diagnostics. `tests/test_slice03.py` verifies
those fixtures, sequence boundaries, and CLI printing/error handling.

### Slice 04: runtime iterators and dynamic context

`open(context, bindings=...)` installs a context and optional bindings before preparing the iterator.
The consumer pulls one value at a time by calling `next()`; operators can pull from child iterators.
`next()` raises `StopIteration` at exhaustion, so null remains an ordinary value.
`reset(context, bindings=...)` rewinds an open iterator, reusing or replacing context and updating bindings.
`close()` releases resources; `DynamicContext` maps names to sequences that iterators can read or update.

`RuntimeIterator` provides lifecycle checks and `_restart`, `_next`, and `_close`
hooks. `LiteralIterator(value)` yields exactly one model value per open/reset.
Repeated close is safe; next/reset on a closed iterator and opening an already
open iterator raise `DynamicError`. Exhaustion remains stable until reset.
Omitting the context on open creates a fresh one; reset retains the current one.
Closing an iterator leaves caller-owned context bindings intact. Missing runtime
bindings raise `DynamicError`; future static analysis must reject unbound query
references with `StaticError` before execution.

Tests and query fixtures are in `tests/test_slice04.py` and
`tests/queries/slice04/cases.json`. Fixtures verify literal iterator output directly;
the CLI continues to report that query evaluation is unimplemented.

## Slice 05: atomic literal expressions

The parser produces a literal AST node. The engine runs it through
`LiteralIterator` and collects the single result. Section 6 leaves literal
spelling unspecified, so this slice uses JSON syntax for numbers and
double-quoted strings, including escapes, and accepts `true`, `false`, and
`null`. A leading minus is accepted as part of a JSON number. Surrounding
JSON whitespace is allowed. Malformed literals raise `StaticError`.

Use `--expr=...` for negative exponent notation so that argparse treats it as
the option's value.

```bash
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m rumblet run --expr=-2.5e-2
.venv/bin/python -m rumblet run --expr '"hello"'
.venv/bin/python -m rumblet run --expr 'null'
```

## Slice 06: parenthesized expressions

Parentheses group expressions, including nested groups. A group evaluates to
the enclosed expression's sequence. Empty parentheses evaluate to an empty
sequence, which the CLI prints as `()`.

## Slice 07: arithmetic

Unary `+` and `-` bind most tightly, followed by `*`, `div`, and `mod`,
then binary `+` and `-`. Binary operators at the same precedence associate
left to right. Parentheses override precedence. Each operand must produce
exactly one number.

Section 9 leaves division and remainder edge cases unspecified. This slice
uses Python true division and remainder (a nonzero remainder has the divisor's
sign). A zero divisor or a result outside the finite number model produces a
dynamic error.

## Slice 08: comma expressions

Comma expressions concatenate their operand sequences from left to right.
Nested expressions contribute individual items, duplicates are preserved,
and empty operands contribute no items. Commas bind more loosely than
arithmetic.

## Slice 09: object constructors

Object constructors emit one object. Member names are string literals and
member values are single expressions. Each member expression must yield
exactly one item. Duplicate names and member values with the wrong cardinality
raise dynamic errors.

## Slice 10: array constructors

Array constructors emit one array, preserving element order. Each element
expression must yield exactly one item. Empty and multi-item element sequences
raise dynamic errors. Arrays and objects can nest inside one another.
