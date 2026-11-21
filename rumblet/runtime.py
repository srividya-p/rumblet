"""Pull-based runtime iterator lifecycle; exhaustion is StopIteration."""

import operator
from abc import ABC, abstractmethod
from collections.abc import Generator

from rumblet.context import DynamicContext
from rumblet.errors import DynamicError
from rumblet.sequence import Sequence
from rumblet.values import (
    ArrayValue,
    AtomicValue,
    BooleanValue,
    NumberValue,
    ObjectValue,
    StringValue,
    Value,
    _require_value,
)


def effective_boolean_value(sequence: Sequence) -> bool:
    """Return the effective boolean value defined by Mini Query Language §10."""
    size = len(sequence)
    if size == 0:
        return False
    if size == 1:
        value = next(iter(sequence))
        if isinstance(value, BooleanValue):
            return value.value
    raise DynamicError("effective boolean value requires an empty sequence or a single boolean")


class RuntimeIterator(ABC):
    """Subclasses implement _next and may use _restart/_close lifecycle hooks."""

    def __init__(self) -> None:
        self._context: DynamicContext | None = None
        self._exhausted = False

    @property
    def context(self) -> DynamicContext:
        if self._context is None:
            raise DynamicError("iterator is not open")
        return self._context

    def open(self, context: DynamicContext | None = None,
             bindings: dict[str, Sequence] | None = None) -> None:
        if self._context is not None:
            raise DynamicError("iterator is already open")
        self._start(context if context is not None else DynamicContext(), bindings)

    def reset(self, context: DynamicContext | None = None,
              bindings: dict[str, Sequence] | None = None) -> None:
        current = self.context  # Requires open, even when replacing the context.
        self._start(context if context is not None else current, bindings)

    def _start(self, context: DynamicContext,
               bindings: dict[str, Sequence] | None) -> None:
        if not isinstance(context, DynamicContext):
            raise DynamicError("iterator context must be a DynamicContext")
        if bindings is not None:
            context.update(bindings)
        self._context = context
        self._exhausted = False
        self._restart()

    def next(self) -> Value:
        if self._context is None:
            raise DynamicError("iterator is not open")
        if self._exhausted:
            raise StopIteration
        try:
            return self._next()
        except StopIteration:
            self._exhausted = True
            raise

    def close(self) -> None:
        if self._context is not None:
            try:
                self._close()
            finally:
                self._context = None

    def _restart(self) -> None:
        """Prepare or rewind state; subclasses may read or update context bindings."""

    def _close(self) -> None:
        """Release subclass resources."""

    @abstractmethod
    def _next(self) -> Value:
        """Return one model value, or raise StopIteration."""


class EmptySequenceIterator(RuntimeIterator):
    """Yield no values."""

    def _next(self) -> Value:
        raise StopIteration


class CommaIterator(RuntimeIterator):
    """Drain each operand in order, opening it only when needed."""

    def __init__(self, operands: tuple[RuntimeIterator, ...]) -> None:
        super().__init__()
        self._operands = operands
        self._items = self._concatenate()

    def _restart(self) -> None:
        self._items.close()
        self._items = self._concatenate()

    def _next(self) -> Value:
        return next(self._items)

    def _close(self) -> None:
        self._items.close()

    def _concatenate(self) -> Generator[Value, None, None]:
        for operand in self._operands:
            operand.open(self.context)
            try:
                while True:
                    yield operand.next()
            except StopIteration:
                pass
            finally:
                operand.close()


class LiteralIterator(RuntimeIterator):
    """Yield one literal value per open/reset cycle."""

    def __init__(self, value: Value) -> None:
        super().__init__()
        try:
            _require_value(value)
        except TypeError as error:
            raise DynamicError("a literal iterator requires one model value") from error
        self._value = value
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _next(self) -> Value:
        if self._emitted:
            raise StopIteration
        self._emitted = True
        return self._value


def _read_effective_boolean(operand: RuntimeIterator, context: DynamicContext) -> bool:
    operand.open(context)
    try:
        values = []
        for _ in range(2):
            try:
                values.append(operand.next())
            except StopIteration:
                break
        return effective_boolean_value(Sequence(values))
    finally:
        operand.close()


class LogicalIterator(RuntimeIterator):
    """Evaluate logical operands and emit one boolean."""

    def __init__(self, operation: str, operands: tuple[RuntimeIterator, ...]) -> None:
        super().__init__()
        self._operation = operation
        self._operands = operands
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _next(self) -> Value:
        if self._emitted:
            raise StopIteration
        operands = [_read_effective_boolean(child, self.context) for child in self._operands]
        if self._operation == "not":
            result = not operands[0]
        elif self._operation == "and":
            result = all(operands)
        else:
            result = any(operands)
        self._emitted = True
        return BooleanValue(result)


class IfIterator(RuntimeIterator):
    """Evaluate the test once per open or reset and pull from the selected branch."""

    def __init__(self, test: RuntimeIterator, then_branch: RuntimeIterator,
                 else_branch: RuntimeIterator) -> None:
        super().__init__()
        self._test = test
        self._then_branch = then_branch
        self._else_branch = else_branch
        self._selected: RuntimeIterator | None = None

    def _restart(self) -> None:
        self._close()

    def _next(self) -> Value:
        if self._selected is None:
            condition = _read_effective_boolean(self._test, self.context)
            selected = self._then_branch if condition else self._else_branch
            selected.open(self.context)
            self._selected = selected
        return self._selected.next()

    def _close(self) -> None:
        selected = self._selected
        self._selected = None
        if selected is not None:
            selected.close()


class ObjectIterator(RuntimeIterator):
    """Evaluate member expressions and emit one object."""

    def __init__(self, members: tuple[tuple[str, RuntimeIterator], ...]) -> None:
        super().__init__()
        self._members = members
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _next(self) -> Value:
        if self._emitted:
            raise StopIteration
        members = {}
        for name, operand in self._members:
            if name in members:
                raise DynamicError(f"duplicate object member name: {name!r}")
            message = f"object member {name!r} must contain exactly one value"
            members[name] = _read_single_value(operand, self.context, message)
        result = ObjectValue(members)
        self._emitted = True
        return result


class ArrayIterator(RuntimeIterator):
    """Evaluate elements in order and emit one array."""

    def __init__(self, elements: tuple[RuntimeIterator, ...]) -> None:
        super().__init__()
        self._elements = elements
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _next(self) -> Value:
        if self._emitted:
            raise StopIteration
        elements = []
        for position, operand in enumerate(self._elements, start=1):
            message = f"array element {position} must contain exactly one value"
            elements.append(_read_single_value(operand, self.context, message))
        result = ArrayValue(elements)
        self._emitted = True
        return result


def _read_single_value(operand: RuntimeIterator, context: DynamicContext, message: str) -> Value:
    operand.open(context)
    try:
        try:
            value = operand.next()
        except StopIteration:
            raise DynamicError(message) from None
        try:
            operand.next()
        except StopIteration:
            return value
        raise DynamicError(message)
    finally:
        operand.close()


class InstanceOfIterator(RuntimeIterator):
    """Test the model kind of a singleton operand and emit one boolean."""

    def __init__(self, operand: RuntimeIterator, type_name: str) -> None:
        super().__init__()
        self._operand = operand
        self._type_name = type_name
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _next(self) -> Value:
        if self._emitted:
            raise StopIteration
        value = _read_single_value(
            self._operand, self.context, "instance of operand must contain exactly one value",
        )
        self._emitted = True
        return BooleanValue(value.kind == self._type_name)


_COMPARISONS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
}


class ComparisonIterator(RuntimeIterator):
    """Compare two singleton atomic operands and emit one boolean."""

    def __init__(self, operation: str, left: RuntimeIterator, right: RuntimeIterator) -> None:
        super().__init__()
        self._compare = _COMPARISONS[operation]
        self._ordering = operation not in ("eq", "ne")
        self._left = left
        self._right = right
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _read_atomic(self, operand: RuntimeIterator) -> AtomicValue:
        message = "comparison operands must contain exactly one atomic value"
        value = _read_single_value(operand, self.context, message)
        if not isinstance(value, AtomicValue):
            raise DynamicError(message)
        return value

    def _next(self) -> Value:
        if self._emitted:
            raise StopIteration
        left = self._read_atomic(self._left)
        right = self._read_atomic(self._right)
        if self._ordering:
            if isinstance(left, NumberValue) and isinstance(right, NumberValue) or isinstance(left, StringValue) and isinstance(right, StringValue):
                result = self._compare(left.value, right.value)
            else:
                raise DynamicError("ordering comparisons require two numbers or two strings")
        else:
            result = self._compare(left, right)
        self._emitted = True
        return BooleanValue(result)


_ARITHMETIC = {
    (1, "+"): operator.pos,
    (1, "-"): operator.neg,
    (2, "+"): operator.add,
    (2, "-"): operator.sub,
    (2, "*"): operator.mul,
    (2, "div"): operator.truediv,
    (2, "mod"): operator.mod,
}


def _read_number(iterator: RuntimeIterator, context: DynamicContext) -> int | float:
    message = "arithmetic operands must contain exactly one number"
    iterator.open(context)
    try:
        try:
            value = iterator.next()
        except StopIteration:
            raise DynamicError(message) from None
        if not isinstance(value, NumberValue):
            raise DynamicError(message)
        try:
            iterator.next()
        except StopIteration:
            return value.value
        raise DynamicError(message)
    finally:
        iterator.close()


def _apply_arithmetic(operation, *operands: float) -> NumberValue:
    try:
        return NumberValue(operation(*operands))
    except ZeroDivisionError:
        raise DynamicError("division or remainder by zero") from None
    except (OverflowError, ValueError) as error:
        raise DynamicError("arithmetic result must be finite") from error


class ArithmeticIterator(RuntimeIterator):
    """Pull singleton numbers from child iterators and emit one result."""

    def __init__(self, operator: str, operands: tuple[RuntimeIterator, ...]) -> None:
        super().__init__()
        self._operation = _ARITHMETIC[len(operands), operator]
        self._operands = operands
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _next(self) -> Value:
        if self._emitted:
            raise StopIteration
        operands = [_read_number(child, self.context) for child in self._operands]
        result = _apply_arithmetic(self._operation, *operands)
        self._emitted = True
        return result


class ArithmeticChainIterator(RuntimeIterator):
    """Fold a binary operator chain in source order."""

    def __init__(self, first: RuntimeIterator,
                 steps: tuple[tuple[str, RuntimeIterator], ...]) -> None:
        super().__init__()
        self._first = first
        self._steps = tuple((_ARITHMETIC[2, operator], operand) for operator, operand in steps)

    def _restart(self) -> None:
        self._emitted = False

    def _next(self) -> Value:
        if self._emitted:
            raise StopIteration
        result = NumberValue(_read_number(self._first, self.context))
        for operation, operand in self._steps:
            right = _read_number(operand, self.context)
            result = _apply_arithmetic(operation, result.value, right)
        self._emitted = True
        return result
