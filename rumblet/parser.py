"""Parse query expressions into AST nodes."""
from __future__ import annotations

import json
import re
from collections.abc import Generator, Iterator
from dataclasses import dataclass

from rumblet.errors import StaticError
from rumblet.values import NULL, AtomicValue, BooleanValue, NumberValue, StringValue


@dataclass(frozen=True, slots=True)
class LiteralExpr:
    value: AtomicValue


@dataclass(frozen=True, slots=True)
class EmptySequenceExpr:
    """The expression ()."""


@dataclass(frozen=True, slots=True)
class VariableRefExpr:
    name: str


@dataclass(frozen=True, slots=True)
class LetExpr:
    bindings: tuple[tuple[str, Expr], ...]
    return_expr: Expr


@dataclass(frozen=True, slots=True)
class ArithmeticExpr:
    operator: str
    operands: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class ArithmeticChainExpr:
    first: Expr
    steps: tuple[tuple[str, Expr], ...]


@dataclass(frozen=True, slots=True)
class LogicalExpr:
    operator: str
    operands: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class ComparisonExpr:
    operator: str
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class InstanceOfExpr:
    operand: Expr
    type_name: str


@dataclass(frozen=True, slots=True)
class IfExpr:
    test: Expr
    then_branch: Expr
    else_branch: Expr


@dataclass(frozen=True, slots=True)
class CommaExpr:
    operands: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class ObjectExpr:
    members: tuple[tuple[str, Expr], ...]


@dataclass(frozen=True, slots=True)
class ArrayExpr:
    elements: tuple[Expr, ...]


Expr = (
    LiteralExpr | EmptySequenceExpr | ArithmeticExpr | ArithmeticChainExpr | LogicalExpr
    | ComparisonExpr | InstanceOfExpr | IfExpr | CommaExpr | ObjectExpr | ArrayExpr
    | VariableRefExpr | LetExpr
)

type _ParseFrame = Generator[_ParseFrame, Expr | None, Expr]

_TOKEN = re.compile(
    r'[ \t\r\n]+|"(?:[^"\\]|\\[\s\S])*"|'
    r'[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|'
    r':=|\$?[a-zA-Z_][a-zA-Z_0-9]*|[\s\S]'
)


def parse(expression: str) -> Expr:
    tokens = (part.group() for part in _TOKEN.finditer(expression)
              if part.group()[0] not in " \t\r\n")
    parser = _Parser(tokens)
    node = _run_frames(parser.comma())
    if parser.current:
        raise StaticError("unexpected token after expression")
    return node


def _run_frames(root: _ParseFrame) -> Expr:
    """Resume grammar rules on a heap-backed stack at nesting boundaries."""
    frames = [root]
    result = None
    while frames:
        try:
            child = frames[-1].send(result)
        except StopIteration as completed:
            frames.pop()
            result = completed.value
        else:
            frames.append(child)
            result = None
    return result


class _Parser:
    # Delegate within one precedence ladder. Yield a separate frame when
    # entering a nested Expr or ExprSingle so nesting does not grow that ladder.
    def __init__(self, tokens: Iterator[str]) -> None:
        self.tokens = tokens
        self.current = next(tokens, "")

    def advance(self) -> str:
        token = self.current
        self.current = next(self.tokens, "")
        return token

    def comma(self) -> _ParseFrame:
        first = yield from self.expr_single()
        if self.current != ",":
            return first
        operands = [first]
        while self.current == ",":
            self.advance()
            operands.append((yield from self.expr_single()))
        return CommaExpr(tuple(operands))

    def expr_single(self) -> _ParseFrame:
        if self.current == "let":
            return (yield from self.let_expr())
        if self.current == "if":
            return (yield from self.conditional())
        return (yield from self.or_expr())

    def let_expr(self) -> _ParseFrame:
        bindings = []
        while self.current == "let":
            self.advance()
            if not self.current.startswith("$") or self.current == "$":
                raise StaticError("expected a variable name after 'let'")
            name = self.advance()[1:]
            if self.current != ":=":
                raise StaticError("expected ':=' after let variable")
            self.advance()
            binding = yield self.expr_single()
            bindings.append((name, binding))
        if self.current != "return":
            raise StaticError("expected 'return' after let clauses")
        self.advance()
        return_expr = yield self.expr_single()
        return LetExpr(tuple(bindings), return_expr)

    def conditional(self) -> _ParseFrame:
        self.advance()
        if self.current != "(":
            raise StaticError("expected '(' after 'if'")
        self.advance()
        test = yield self.comma()
        if self.current != ")":
            raise StaticError("expected ')' after if test")
        self.advance()
        if self.current != "then":
            raise StaticError("expected 'then' after if test")
        self.advance()
        then_branch = yield self.expr_single()
        if self.current != "else":
            raise StaticError("expected 'else' after then branch")
        self.advance()
        else_branch = yield self.expr_single()
        return IfExpr(test, then_branch, else_branch)

    def or_expr(self) -> _ParseFrame:
        node = yield from self.and_expr()
        while self.current == "or":
            self.advance()
            right = yield from self.and_expr()
            node = LogicalExpr("or", (node, right))
        return node

    def and_expr(self) -> _ParseFrame:
        node = yield from self.not_expr()
        while self.current == "and":
            self.advance()
            right = yield from self.not_expr()
            node = LogicalExpr("and", (node, right))
        return node

    def not_expr(self) -> _ParseFrame:
        if self.current != "not":
            return (yield from self.comparison())
        self.advance()
        if self.current != "(":
            raise StaticError("expected '(' after not")
        self.advance()
        operand = yield self.comma()
        if self.current != ")":
            raise StaticError("expected ')' after not operand")
        self.advance()
        return LogicalExpr("not", (operand,))

    def comparison(self) -> _ParseFrame:
        left = yield from self.additive()
        if self.current in ("eq", "ne", "lt", "le", "gt", "ge"):
            operator = self.advance()
            right = yield from self.additive()
            return ComparisonExpr(operator, left, right)
        if self.current == "instance":
            self.advance()
            if self.current != "of":
                raise StaticError("expected 'of' after 'instance'")
            self.advance()
            if self.current not in ("string", "number", "boolean", "null", "object", "array"):
                raise StaticError("expected a built-in type name after 'instance of'")
            return InstanceOfExpr(left, self.advance())
        return left

    def additive(self) -> _ParseFrame:
        first = yield from self.multiplicative()
        steps = []
        while self.current in ("+", "-"):
            operator = self.advance()
            operand = yield from self.multiplicative()
            steps.append((operator, operand))
        return ArithmeticChainExpr(first, tuple(steps)) if steps else first

    def multiplicative(self) -> _ParseFrame:
        first = yield from self.unary()
        steps = []
        while self.current in ("*", "div", "mod"):
            operator = self.advance()
            operand = yield from self.unary()
            steps.append((operator, operand))
        return ArithmeticChainExpr(first, tuple(steps)) if steps else first

    def unary(self) -> _ParseFrame:
        operators = []
        while self.current in ("+", "-"):
            operators.append(self.advance())
        node = yield from self.primary()
        for operator in reversed(operators):
            node = ArithmeticExpr(operator, (node,))
        return node

    def primary(self) -> _ParseFrame:
        if self.current == "$":
            raise StaticError("expected a variable name immediately after '$'")
        if self.current.startswith("$"):
            return VariableRefExpr(self.advance()[1:])
        if self.current == "{":
            return (yield from self.object_constructor())
        if self.current == "[":
            return (yield from self.array_constructor())
        if self.current == "(":
            self.advance()
            if self.current == ")":
                self.advance()
                return EmptySequenceExpr()
            if not self.current:
                raise StaticError("expected a closing parenthesis")
            node = yield self.comma()
            if self.current != ")":
                raise StaticError("expected a closing parenthesis")
            self.advance()
            return node
        return _parse_literal(self.advance())

    def object_constructor(self) -> _ParseFrame:
        self.advance()
        members = []
        if self.current != "}":
            while True:
                if not self.current.startswith('"'):
                    raise StaticError("expected a string literal as an object member name")
                name = _parse_literal(self.advance()).value.value
                if self.current != ":":
                    raise StaticError("expected ':' after object member name")
                self.advance()
                value = yield self.expr_single()
                members.append((name, value))
                if self.current != ",":
                    break
                self.advance()
        if self.current != "}":
            raise StaticError("expected a closing brace")
        self.advance()
        return ObjectExpr(tuple(members))

    def array_constructor(self) -> _ParseFrame:
        self.advance()
        elements = []
        if self.current != "]":
            elements.append((yield self.expr_single()))
            while self.current == ",":
                self.advance()
                elements.append((yield self.expr_single()))
        if self.current != "]":
            raise StaticError("expected a closing bracket")
        self.advance()
        return ArrayExpr(tuple(elements))


def _parse_literal(source: str) -> LiteralExpr:
    if not source or source[0] not in '"-0123456789tfn':
        raise StaticError("expected a single atomic literal")

    try:
        payload = json.loads(source)
        if payload is None:
            return LiteralExpr(NULL)
        if type(payload) is bool:
            return LiteralExpr(BooleanValue(payload))
        if type(payload) is str:
            return LiteralExpr(StringValue(payload))
        return LiteralExpr(NumberValue(payload))
    except (ValueError, TypeError) as error:
        raise StaticError("invalid atomic literal") from error
