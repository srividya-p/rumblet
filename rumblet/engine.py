"""Parse a query, run its iterator, and collect the result sequence."""

from collections.abc import Generator

from rumblet.errors import DynamicError, StaticError
from rumblet.parser import (
    ArithmeticChainExpr,
    ArithmeticExpr,
    ArrayExpr,
    CommaExpr,
    ComparisonExpr,
    EmptySequenceExpr,
    Expr,
    IfExpr,
    InstanceOfExpr,
    LetExpr,
    LogicalExpr,
    ObjectExpr,
    VariableRefExpr,
    parse,
)
from rumblet.runtime import (
    ArithmeticChainIterator,
    ArithmeticIterator,
    ArrayIterator,
    CommaIterator,
    ComparisonIterator,
    EmptySequenceIterator,
    IfIterator,
    InstanceOfIterator,
    LetIterator,
    LiteralIterator,
    LogicalIterator,
    ObjectIterator,
    RuntimeIterator,
    VariableIterator,
)
from rumblet.sequence import Sequence


def _build_iterator(node: Expr) -> RuntimeIterator:
    """Build child iterators before their parents using an explicit stack."""
    bound_names = frozenset()
    frames = [(_iterator_frame(node, bound_names), bound_names)]
    result: RuntimeIterator | None = None
    while True:
        frame, bound_names = frames[-1]
        try:
            child = next(frame) if result is None else frame.send(result)
        except StopIteration as completed:
            frames.pop()
            if not frames:
                return completed.value
            result = completed.value
        else:
            if isinstance(child, tuple):
                child, bound_names = child
            frames.append((_iterator_frame(child, bound_names), bound_names))
            result = None


type _BuildFrame[Result] = Generator[Expr | tuple[Expr, frozenset[str]], RuntimeIterator, Result]


def _build_children(nodes: tuple[Expr, ...]) -> _BuildFrame[tuple[RuntimeIterator, ...]]:
    children = []
    for node in nodes:
        children.append((yield node))
    return tuple(children)


def _iterator_frame(node: Expr, bound_names: frozenset[str]) -> _BuildFrame[RuntimeIterator]:
    if isinstance(node, EmptySequenceExpr):
        return EmptySequenceIterator()
    if isinstance(node, VariableRefExpr):
        if node.name not in bound_names:
            raise StaticError(f"unbound variable: ${node.name}")
        return VariableIterator(node.name)
    if isinstance(node, LetExpr):
        bindings = []
        for name, binding in node.bindings:
            child = yield (binding, bound_names)
            bindings.append((name, child))
            bound_names = bound_names | {name}
        return_iterator = yield (node.return_expr, bound_names)
        return LetIterator(tuple(bindings), return_iterator)
    if isinstance(node, ArithmeticExpr):
        operands = yield from _build_children(node.operands)
        return ArithmeticIterator(node.operator, operands)
    if isinstance(node, ArithmeticChainExpr):
        first = yield node.first
        steps = []
        for operator, operand in node.steps:
            child = yield operand
            steps.append((operator, child))
        return ArithmeticChainIterator(first, tuple(steps))
    if isinstance(node, LogicalExpr):
        operands = yield from _build_children(node.operands)
        return LogicalIterator(node.operator, operands)
    if isinstance(node, ComparisonExpr):
        left = yield node.left
        right = yield node.right
        return ComparisonIterator(node.operator, left, right)
    if isinstance(node, InstanceOfExpr):
        operand = yield node.operand
        return InstanceOfIterator(operand, node.type_name)
    if isinstance(node, IfExpr):
        test = yield node.test
        then_branch = yield node.then_branch
        else_branch = yield node.else_branch
        return IfIterator(test, then_branch, else_branch)
    if isinstance(node, CommaExpr):
        operands = yield from _build_children(node.operands)
        return CommaIterator(operands)
    if isinstance(node, ObjectExpr):
        members = []
        for name, value in node.members:
            child = yield value
            members.append((name, child))
        return ObjectIterator(tuple(members))
    if isinstance(node, ArrayExpr):
        elements = yield from _build_children(node.elements)
        return ArrayIterator(elements)
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
