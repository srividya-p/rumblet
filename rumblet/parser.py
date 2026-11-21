"""Parse query expressions into AST nodes."""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
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
)

_TOKEN = re.compile(
    r'[ \t\r\n]+|"(?:[^"\\]|\\[\s\S])*"|'
    r'[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|'
    r'[a-zA-Z_][a-zA-Z_0-9]*|[\s\S]'
)


def parse(expression: str) -> Expr:
    tokens = (part.group() for part in _TOKEN.finditer(expression)
              if part.group()[0] not in " \t\r\n")
    parser = _Parser(tokens)
    try:
        node = parser.comma()
    except RecursionError as error:
        raise StaticError("expression nesting is too deep") from error
    if parser.current:
        raise StaticError("unexpected token after expression")
    return node


class _Parser:
    def __init__(self, tokens: Iterator[str]) -> None:
        self.tokens = tokens
        self.current = next(tokens, "")

    def advance(self) -> str:
        token = self.current
        self.current = next(self.tokens, "")
        return token

    def comma(self) -> Expr:
        first = self.expr_single()
        if self.current != ",":
            return first
        operands = [first]
        while self.current == ",":
            self.advance()
            operands.append(self.expr_single())
        return CommaExpr(tuple(operands))

    def expr_single(self) -> Expr:
        if self.current == "if":
            return self.conditional()
        return self.or_expr()

    def conditional(self) -> IfExpr:
        self.advance()
        if self.current != "(":
            raise StaticError("expected '(' after 'if'")
        self.advance()
        test = self.comma()
        if self.current != ")":
            raise StaticError("expected ')' after if test")
        self.advance()
        if self.current != "then":
            raise StaticError("expected 'then' after if test")
        self.advance()
        then_branch = self.expr_single()
        if self.current != "else":
            raise StaticError("expected 'else' after then branch")
        self.advance()
        return IfExpr(test, then_branch, self.expr_single())

    def or_expr(self) -> Expr:
        node = self.and_expr()
        while self.current == "or":
            self.advance()
            node = LogicalExpr("or", (node, self.and_expr()))
        return node

    def and_expr(self) -> Expr:
        node = self.not_expr()
        while self.current == "and":
            self.advance()
            node = LogicalExpr("and", (node, self.not_expr()))
        return node

    def not_expr(self) -> Expr:
        if self.current != "not":
            return self.comparison()
        self.advance()
        if self.current != "(":
            raise StaticError("expected '(' after not")
        self.advance()
        operand = self.comma()
        if self.current != ")":
            raise StaticError("expected ')' after not operand")
        self.advance()
        return LogicalExpr("not", (operand,))

    def comparison(self) -> Expr:
        left = self.additive()
        if self.current in ("eq", "ne", "lt", "le", "gt", "ge"):
            operator = self.advance()
            return ComparisonExpr(operator, left, self.additive())
        if self.current == "instance":
            self.advance()
            if self.current != "of":
                raise StaticError("expected 'of' after 'instance'")
            self.advance()
            if self.current not in ("string", "number", "boolean", "null", "object", "array"):
                raise StaticError("expected a built-in type name after 'instance of'")
            return InstanceOfExpr(left, self.advance())
        return left

    def additive(self) -> Expr:
        first = self.multiplicative()
        steps = []
        while self.current in ("+", "-"):
            operator = self.advance()
            steps.append((operator, self.multiplicative()))
        return ArithmeticChainExpr(first, tuple(steps)) if steps else first

    def multiplicative(self) -> Expr:
        first = self.unary()
        steps = []
        while self.current in ("*", "div", "mod"):
            operator = self.advance()
            steps.append((operator, self.unary()))
        return ArithmeticChainExpr(first, tuple(steps)) if steps else first

    def unary(self) -> Expr:
        operators = []
        while self.current in ("+", "-"):
            operators.append(self.advance())
        node = self.primary()
        for operator in reversed(operators):
            node = ArithmeticExpr(operator, (node,))
        return node

    def primary(self) -> Expr:
        if self.current == "{":
            return self.object_constructor()
        if self.current == "[":
            return self.array_constructor()
        if self.current == "(":
            self.advance()
            if self.current == ")":
                self.advance()
                return EmptySequenceExpr()
            if not self.current:
                raise StaticError("expected a closing parenthesis")
            node = self.comma()
            if self.current != ")":
                raise StaticError("expected a closing parenthesis")
            self.advance()
            return node
        return _parse_literal(self.advance())

    def object_constructor(self) -> ObjectExpr:
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
                members.append((name, self.expr_single()))
                if self.current != ",":
                    break
                self.advance()
        if self.current != "}":
            raise StaticError("expected a closing brace")
        self.advance()
        return ObjectExpr(tuple(members))

    def array_constructor(self) -> ArrayExpr:
        self.advance()
        elements = []
        if self.current != "]":
            elements.append(self.expr_single())
            while self.current == ",":
                self.advance()
                elements.append(self.expr_single())
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
