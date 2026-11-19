"""Parse a query, run its iterator, and collect the result sequence."""

from rumblet.errors import DynamicError
from rumblet.parser import (
    ArithmeticExpr,
    ArrayExpr,
    CommaExpr,
    ComparisonExpr,
    EmptySequenceExpr,
    Expr,
    IfExpr,
    InstanceOfExpr,
    LogicalExpr,
    ObjectExpr,
    parse,
)
from rumblet.runtime import (
    ArithmeticIterator,
    ArrayIterator,
    CommaIterator,
    ComparisonIterator,
    EmptySequenceIterator,
    IfIterator,
    InstanceOfIterator,
    LiteralIterator,
    LogicalIterator,
    ObjectIterator,
    RuntimeIterator,
)
from rumblet.sequence import Sequence


def _build_iterator(node: Expr) -> RuntimeIterator:
    if isinstance(node, EmptySequenceExpr):
        return EmptySequenceIterator()
    if isinstance(node, ArithmeticExpr):
        return ArithmeticIterator(node.operator, tuple(map(_build_iterator, node.operands)))
    if isinstance(node, LogicalExpr):
        return LogicalIterator(node.operator, tuple(map(_build_iterator, node.operands)))
    if isinstance(node, ComparisonExpr):
        return ComparisonIterator(node.operator, _build_iterator(node.left), _build_iterator(node.right))
    if isinstance(node, InstanceOfExpr):
        return InstanceOfIterator(_build_iterator(node.operand), node.type_name)
    if isinstance(node, IfExpr):
        return IfIterator(
            _build_iterator(node.test),
            _build_iterator(node.then_branch),
            _build_iterator(node.else_branch),
        )
    if isinstance(node, CommaExpr):
        return CommaIterator(tuple(map(_build_iterator, node.operands)))
    if isinstance(node, ObjectExpr):
        return ObjectIterator(tuple(
            (name, _build_iterator(value)) for name, value in node.members
        ))
    if isinstance(node, ArrayExpr):
        return ArrayIterator(tuple(map(_build_iterator, node.elements)))
    return LiteralIterator(node.value)


def evaluate(expression: str) -> Sequence:
    node = parse(expression)
    values = []
    try:
        iterator = _build_iterator(node)
        iterator.open()
        try:
            while True:
                values.append(iterator.next())
        except StopIteration:
            return Sequence(values)
        finally:
            iterator.close()
    except RecursionError as error:
        raise DynamicError("expression is too deep to evaluate") from error
