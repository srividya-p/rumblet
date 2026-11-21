# rumblet

A local Python toy query engine. Behavior is defined exclusively by
`mini-data-model.html` and `mini-query-language.html`.

## Unit tests

Use the local uv-managed virtual environment. Rumblet requires Python 3.12
or newer and has no package dependencies. Run these commands from the repo root.

```bash
$ python -m unittest discover -s tests -q
----------------------------------------------------------------------
Ran 54 tests in 2.456s

OK
```

Each slice has unit tests in `tests/test_sliceNN.py` and query fixtures in
`tests/queries/sliceNN/cases.json`. The fixtures record expected results at
the CLI or for the model or runtime API covered by the slice.

## Run queries

```bash
$ python -m rumblet run --expr '1 + 2, null'
3
null
```

The CLI accepts inline expressions through `run --expr`, including FLWOR
expressions with mixed `for` and `let` clauses and an optional `where`.
File input and function calls are pending.

## Slices 00–04: foundations

### Slice 00: initialization

Slice 00 established the package, CLI scaffold, and tests. The engine now
parses a query into an abstract syntax tree, builds runtime iterators
(`open` / `next` / `close` / `reset`), and collects their output into the
sequence printed by the CLI.

### Slice 01: atomic values

`rumblet.values` implements immutable `StringValue`, `NumberValue`,
`BooleanValue`, and `NullValue` (also available as `NULL`). Equality compares
kind and content; separately constructed nulls represent the same model value.
Strings reject surrogate code points and count Unicode scalar values with `len`.
No Unicode normalization is performed.

All atomic `.value` payloads are compatible with Python's standard JSON encoder
and decoder: strings, integers or finite floats, booleans, and `None` for null.
Integers and floats share the JSON kind `number`. Booleans are a distinct kind.
The spec leaves numeric precision unspecified. Fractional numbers use Python's
float precision. NaN and infinities are rejected. Model values reject implicit
Python truth conversion. Slice 11 defines how query sequences are tested as booleans.

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

### Slice 03: sequences, printing, and errors

`Sequence([value, ...])` is a list-backed query sequence, separate from `Value`.
It preserves order and duplicates, accepts only model values, and cannot occur
inside an array, object, or another sequence. Its `.values` property returns a
copy of the list. `print_sequence(sequence, file=...)` prints one compact JSON
value per line, or `()` followed by a newline for an empty sequence. Object keys
are sorted for reproducible output, and strings retain JSON quotes and escapes.
This output convention is an implementation choice because the specs do not
define serialization. Empty arrays and null print as `[]` and `null` respectively.

`StaticError` and `DynamicError` in `rumblet.errors` distinguish static query
failures from invalid runtime operations. The CLI reports both on stderr and
exits with code 2.

### Slice 04: runtime iterators and dynamic context

`open(context, bindings=...)` installs a context and optional bindings before preparing the iterator.
The consumer pulls one value at a time by calling `next()`, and operators can pull from child iterators.
`next()` raises `StopIteration` at exhaustion, so null remains an ordinary value.
`reset(context, bindings=...)` rewinds an open iterator, reusing or replacing context and updating bindings.
`close()` releases resources. `DynamicContext` maps names to sequences that iterators can read or update.

`RuntimeIterator` provides lifecycle checks and `_restart`, `_next`, and `_close`
hooks. `LiteralIterator(value)` yields exactly one model value per open/reset.
Repeated close is safe. Calling next or reset on a closed iterator or opening an already
open iterator raise `DynamicError`. Exhaustion remains stable until reset.
Omitting the context on open creates a fresh one. Reset retains the current one by default.
Closing an iterator leaves caller-owned context bindings intact. Missing runtime
bindings raise `DynamicError`. Future static analysis must reject unbound query
references with `StaticError` before execution.

## Slice 05: atomic literal expressions

The parser produces a literal AST node. The engine runs it through
`LiteralIterator` and collects the single result. Section 6 leaves literal
spelling unspecified, so this slice uses JSON syntax for numbers and
double-quoted strings, including escapes, and accepts `true`, `false`, and
`null`. Unary signs are handled by the arithmetic grammar. Surrounding
JSON whitespace is allowed. Malformed literals raise `StaticError`.

```bash
$ python -m rumblet run --expr 1e+2
100.0

$ python -m rumblet run --expr '""'
""

$ python -m rumblet run --expr null
null
```

## Slice 06: parenthesized expressions

Parentheses group expressions, including nested groups. A group evaluates to
the enclosed expression's sequence. Empty parentheses evaluate to an empty
sequence, which the CLI prints as `()`.

```bash
$ python -m rumblet run --expr '()'
()

$ python -m rumblet run --expr '(42)'
42

$ python -m rumblet run --expr '((null))'
null
```

## Slice 07: arithmetic

Unary `+` and `-` bind most tightly, followed by `*`, `div`, and `mod`,
then binary `+` and `-`. Binary operators at the same precedence associate
left to right. Parentheses override precedence. Each operand must produce
exactly one number.

Section 9 leaves division and remainder edge cases unspecified. This slice
uses Python true division and remainder (a nonzero remainder has the divisor's
sign). A zero divisor or a result outside the finite number model produces a
dynamic error.

```bash
$ python -m rumblet run --expr '2 + 3 * 4'
14

$ python -m rumblet run --expr '(2 + 3) * 4'
20

$ python -m rumblet run --expr '7 div 2'
3.5
```

## Slice 08: comma expressions

Comma expressions concatenate their operand sequences from left to right.
Nested expressions contribute individual items, duplicates are preserved,
and empty operands contribute no items. Commas bind more loosely than
arithmetic.

```bash
$ python -m rumblet run --expr '1, 2, 3'
1
2
3

$ python -m rumblet run --expr '(1, (2, (), 2)), (), null'
1
2
2
null
```

## Slice 09: object constructors

Object constructors emit one object. Member names are string literals and
member values are single expressions. Each member expression must yield
exactly one item. Duplicate names and member values with the wrong cardinality
raise dynamic errors.

```bash
$ python -m rumblet run --expr '{}'
{}

$ python -m rumblet run --expr '{ "b": 1 + 2, "a": null }'
{"a":null,"b":3}
```

## Slice 10: array constructors

Array constructors emit one array, preserving element order. Each element
expression must yield exactly one item. Empty and multi-item element sequences
raise dynamic errors. Arrays and objects can nest inside one another.

```bash
$ python -m rumblet run --expr '[]'
[]

$ python -m rumblet run --expr '[3, 1 + 1, 3, ((), null), false]'
[3,2,3,null,false]
```

## Slice 11: effective boolean value and logic

Per §10, an empty sequence has effective boolean value false. A singleton
boolean has the value of that boolean. Every other sequence raises
`DynamicError`. The `effective_boolean_value()` helper is in `rumblet.runtime`.

`not(Expr)`, `and`, and `or` each produce one boolean, in descending order
of precedence. The spec leaves operand evaluation order unspecified.
Rumblet evaluates operands left to right and checks both operands of `and`
and `or` when the left operand succeeds.

```bash
$ python -m rumblet run --expr 'true or false and false'
true

$ python -m rumblet run --expr 'not((), true) and false'
false
```

## Slice 12: value comparisons

Per §11, `eq`, `ne`, `lt`, `le`, `gt`, and `ge` require one atomic value
per operand and produce one boolean. Equality uses the data model's kind and
value rules. Ordering requires two numbers or two strings. Strings are ordered
lexicographically by Unicode scalar value. Comparisons bind between arithmetic
and logic, and chaining requires parentheses.

```bash
$ python -m rumblet run --expr '1 eq 1.0, true eq true, null eq null, "a" eq "a"'
true
true
true
true

$ python -m rumblet run --expr '1 lt 2, 2 le 2, 2 gt 1, 1 ge 2'
true
true
true
false
```

## Slice 13: instance tests

Per §13, `instance of` checks a singleton value against one of six built-in type
names (`string`, `number`, `boolean`, `null`, `object`, or `array`) and returns
one boolean. An empty or multi-item operand raises `DynamicError`. An unknown
type name raises `StaticError`.

```bash
$ python -m rumblet run --expr 'true instance of number, [] instance of object, null instance of boolean'
false
false
false

$ python -m rumblet run --expr '1 + 2 instance of number and not("x" instance of array)'
true
```

## Slice 14: conditional expressions

Per §15, `if (Expr) then ExprSingle else ExprSingle` uses the effective
boolean value of the test. Only the selected branch is evaluated, and the
conditional returns that branch's entire sequence. Use parentheses around a
comma expression when it should form a single branch.

```bash
$ python -m rumblet run --expr 'if (true) then 1 else 1 div 0'
1

$ python -m rumblet run --expr 'if (false) then 1 div 0 else (2, 3)'
2
3
```

## Slice 15: variable references and let clauses

Per §§8 and 12, a `$name` reference returns the entire bound sequence.
Each `let` clause binds its initializer's sequence, including empty sequences,
and the `return` expression evaluates once after all bindings are established.
Later clauses can reference earlier bindings. An unbound reference raises
`StaticError` before evaluation.

The spec leaves variable name syntax and repeated bindings unspecified. Names
use ASCII letters or underscores at the start, followed by ASCII letters,
digits, or underscores, immediately after `$`. A later binding of the same
name shadows the earlier one after its initializer finishes.

```bash
$ python -m rumblet run --expr 'let $x := (1,2) return $x'
1
2

$ python -m rumblet run --expr 'let $x := 2 let $y := ($x, $x + 1) return $y'
2
3

$ python -m rumblet run --expr 'let $x := () return 7'
7
```

## Slice 16: for expressions

Per §12, `for $name in ExprSingle return ExprSingle` pulls one value at a time
from the input sequence and binds it as a singleton sequence. The return
iterator resets for every binding, and its results are concatenated in input
order. An empty input yields an empty sequence without evaluating the return
expression. The loop variable is in scope in the return expression. The input
expression uses the surrounding scope.

```bash
$ python -m rumblet run --expr 'for $x in (1,2,3) return $x + 10'
11
12
13

$ python -m rumblet run --expr 'for $x in (1,2) return ($x,$x)'
1
1
2
2

$ python -m rumblet run --expr 'for $x in () return 1 div 0'
()
```

## Slice 17: where clauses

Per §12, an optional `where ExprSingle` goes after the `for` or `let` bindings
and before `return`. The predicate can reference those bindings and is evaluated
once per tuple. A singleton `true` keeps the tuple and evaluates `return`.
An empty sequence or a singleton `false` drops the tuple and skips `return`.
Any other predicate result raises `DynamicError` under the effective boolean
value rules in §10.

```bash
$ python -m rumblet run --expr 'for $x in (1,2,3,4) where $x mod 2 eq 0 return $x'
2
4

$ python -m rumblet run --expr 'let $x := (1,2) let $keep := true where $keep return $x'
1
2

$ python -m rumblet run --expr 'for $x in (1,2) where () return 1 div 0'
()
```

## Slice 18: full FLWOR expressions

Per §§5 and 12, a FLWOR expression starts with `for` or `let` and accepts
any mix of those clauses before an optional `where` and a required `return`.
Each `for` iterates its input for every tuple produced by the preceding
clauses. Each `let` binds its full sequence once per incoming tuple. Later
clauses can reference earlier bindings. The `where` clause filters complete
tuples, and the return sequences are concatenated in iteration order.

```bash
$ python -m rumblet run --expr 'for $team in ("a","b") for $score in (1,2,3) where $score gt 1 and ($team eq "a" or $score eq 3) return {"team":$team,"scores":[$score,$score * 10]}'
{"scores":[2,20],"team":"a"}
{"scores":[3,30],"team":"a"}
{"scores":[3,30],"team":"b"}

$ python -m rumblet run --expr 'let $bases := (2,4) for $base in $bases let $offsets := (1,2) for $offset in $offsets let $total := $base + $offset where $total ge 5 return [{"total":$total},[$base,$offset]]'
[{"total":5},[4,1]]
[{"total":6},[4,2]]

$ python -m rumblet run --expr 'for $x in (1,2) let $original := $x let $tags := if ($x eq 1) then ("low","first") else "high" for $tag in $tags let $x := $x * 10 return {"tag":$tag,"values":[$original,$x]}'
{"tag":"low","values":[1,10]}
{"tag":"first","values":[1,10]}
{"tag":"high","values":[2,20]}
```
