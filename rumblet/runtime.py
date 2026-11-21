"""Pull-based runtime iterator lifecycle; exhaustion is StopIteration."""

import operator
from abc import ABC, abstractmethod
from collections.abc import Generator, Iterator

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
        """Close the active iterators and release their contexts even on failure."""
        active = []
        first_error: BaseException | None = None
        pending = [self]
        try:
            while pending:
                iterator = pending.pop()
                if iterator._context is None:
                    continue
                active.append(iterator)
                pending.extend(reversed(iterator._detach_children()))
                try:
                    iterator._close()
                except BaseException as error:  # noqa: BLE001
                    if first_error is None:
                        first_error = error
        finally:
            for iterator in reversed(active):
                iterator._context = None
        if first_error is not None:
            raise first_error

    def _restart(self) -> None:
        """Prepare or rewind state; subclasses may read or update context bindings."""

    def _close(self) -> None:
        """Release subclass resources."""

    def _detach_child(self) -> "RuntimeIterator | None":
        """Release ownership of the child held open between pulls."""
        return None

    def _detach_children(self) -> "tuple[RuntimeIterator, ...]":
        child = self._detach_child()
        return () if child is None else (child,)

    @abstractmethod
    def _next(self) -> Value:
        """Return one model value, or raise StopIteration."""


type _Pull[Result] = Generator[RuntimeIterator, Value | None, Result]


class _CompositeIterator(RuntimeIterator):
    """An iterator whose pull can suspend while a child produces a value."""

    @abstractmethod
    def _pull(self) -> _Pull[Value | None]:
        """Yield requests for child items. Return None at exhaustion."""

    def _next(self) -> Value:
        # Each suspended frame asks for one child item. Deliver failures back
        # into those frames so operand readers run their cleanup on errors.
        frames = [(self, self._pull())]
        result = None
        error = None
        while True:
            iterator, frame = frames[-1]
            try:
                if error is None:
                    child = frame.send(result)
                else:
                    pending, error = error, None
                    child = frame.throw(pending)
            except StopIteration as completed:
                frames.pop()
                result = completed.value
                if result is None:
                    iterator._exhausted = True
                if not frames:
                    if result is None:
                        raise StopIteration from None
                    return result
                continue
            except BaseException as failure:
                frames.pop()
                if not frames:
                    raise
                error = failure
                continue

            try:
                if isinstance(child, _CompositeIterator):
                    _ = child.context
                    if not child._exhausted:
                        frames.append((child, child._pull()))
                    result = None
                else:
                    result = child.next()
            except StopIteration:
                result = None
            except BaseException as failure:  # noqa: BLE001
                error = failure


class EmptySequenceIterator(RuntimeIterator):
    """Yield no values."""

    def _next(self) -> Value:
        raise StopIteration


class CommaIterator(_CompositeIterator):
    """Drain each operand in order, opening it only when needed."""

    def __init__(self, operands: tuple[RuntimeIterator, ...]) -> None:
        super().__init__()
        self._operands = operands
        self._index = 0
        self._child: RuntimeIterator | None = None

    def _restart(self) -> None:
        child = self._detach_child()
        if child is not None:
            child.close()
        self._index = 0

    def _detach_child(self) -> RuntimeIterator | None:
        child, self._child = self._child, None
        return child

    def _pull(self) -> _Pull[Value | None]:
        try:
            while self._index < len(self._operands):
                child = self._child
                if child is None:
                    child = self._operands[self._index]
                    child.open(self.context)
                    self._child = child
                item = yield child
                if item is not None:
                    return item
                self._child = None
                child.close()
                self._index += 1
        except BaseException:
            self._index = len(self._operands)
            child = self._detach_child()
            if child is not None:
                child.close()
            raise
        return None


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


class VariableIterator(RuntimeIterator):
    """Yield the sequence bound to a variable in the current context."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name
        self._values: Iterator[Value] | None = None

    def _restart(self) -> None:
        self._values = None

    def _close(self) -> None:
        self._values = None

    def _next(self) -> Value:
        if self._values is None:
            self._values = iter(self.context.lookup(self._name))
        return next(self._values)


class LetIterator(_CompositeIterator):
    """Bind each complete sequence in a private scope, then pull the return."""

    def __init__(self, bindings: tuple[tuple[str, RuntimeIterator], ...],
                 return_iterator: RuntimeIterator) -> None:
        super().__init__()
        self._bindings = bindings
        self._return = return_iterator
        self._active_return: RuntimeIterator | None = None

    def _restart(self) -> None:
        child = self._detach_child()
        if child is not None:
            child.close()

    def _detach_child(self) -> RuntimeIterator | None:
        child, self._active_return = self._active_return, None
        return child

    def _pull(self) -> _Pull[Value | None]:
        if self._active_return is None:
            scope = self.context.copy()
            for name, binding in self._bindings:
                values = []
                binding.open(scope)
                try:
                    while (item := (yield binding)) is not None:
                        values.append(item)
                finally:
                    binding.close()
                scope.bind(name, Sequence(values))
            self._return.open(scope)
            self._active_return = self._return
        return (yield self._active_return)


class ForIterator(_CompositeIterator):
    """Stream the source and concatenate the return sequence for each item."""

    def __init__(self, name: str, source: RuntimeIterator,
                 return_iterator: RuntimeIterator) -> None:
        super().__init__()
        self._name = name
        self._source = source
        self._return = return_iterator
        self._source_open = False
        self._return_open = False
        self._has_binding = False

    def _detach_children(self) -> tuple[RuntimeIterator, ...]:
        children = []
        if self._return_open:
            children.append(self._return)
        if self._source_open:
            children.append(self._source)
        self._return_open = self._source_open = self._has_binding = False
        return tuple(children)

    def _restart(self) -> None:
        children = self._detach_children()
        if children:
            try:
                children[0].close()
            finally:
                for child in children[1:]:
                    child.close()

    def _pull(self) -> _Pull[Value | None]:
        if not self._source_open:
            self._source_open = True
            self._source.open(self.context)
        while True:
            if self._has_binding:
                result = yield self._return
                if result is not None:
                    return result
            item = yield self._source
            if item is None:
                return None
            if not self._return_open:
                scope = self.context.copy()
                scope.bind(self._name, Sequence([item]))
                self._return_open = True
                self._return.open(scope)
                self._return.reset()
            else:
                self._return.reset(bindings={self._name: Sequence([item])})
            self._has_binding = True


def _read_effective_boolean(operand: RuntimeIterator, context: DynamicContext) -> _Pull[bool]:
    operand.open(context)
    try:
        values = []
        for _ in range(2):
            item = yield operand
            if item is None:
                break
            values.append(item)
        return effective_boolean_value(Sequence(values))
    finally:
        operand.close()


class LogicalIterator(_CompositeIterator):
    """Evaluate logical operands and emit one boolean."""

    def __init__(self, operation: str, operands: tuple[RuntimeIterator, ...]) -> None:
        super().__init__()
        self._operation = operation
        self._operands = operands
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _pull(self) -> _Pull[Value | None]:
        if self._emitted:
            return None
        operands = []
        for child in self._operands:
            operands.append((yield from _read_effective_boolean(child, self.context)))
        if self._operation == "not":
            result = not operands[0]
        elif self._operation == "and":
            result = all(operands)
        else:
            result = any(operands)
        self._emitted = True
        return BooleanValue(result)


class IfIterator(_CompositeIterator):
    """Evaluate the test once per open or reset and pull from the selected branch."""

    def __init__(self, test: RuntimeIterator, then_branch: RuntimeIterator,
                 else_branch: RuntimeIterator) -> None:
        super().__init__()
        self._test = test
        self._then_branch = then_branch
        self._else_branch = else_branch
        self._selected: RuntimeIterator | None = None

    def _restart(self) -> None:
        child = self._detach_child()
        if child is not None:
            child.close()

    def _pull(self) -> _Pull[Value | None]:
        if self._selected is None:
            condition = yield from _read_effective_boolean(self._test, self.context)
            selected = self._then_branch if condition else self._else_branch
            selected.open(self.context)
            self._selected = selected
        return (yield self._selected)

    def _detach_child(self) -> RuntimeIterator | None:
        selected, self._selected = self._selected, None
        return selected


class ObjectIterator(_CompositeIterator):
    """Evaluate member expressions and emit one object."""

    def __init__(self, members: tuple[tuple[str, RuntimeIterator], ...]) -> None:
        super().__init__()
        self._members = members
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _pull(self) -> _Pull[Value | None]:
        if self._emitted:
            return None
        members = {}
        for name, operand in self._members:
            if name in members:
                raise DynamicError(f"duplicate object member name: {name!r}")
            message = f"object member {name!r} must contain exactly one value"
            members[name] = yield from _read_single_value(operand, self.context, message)
        result = ObjectValue(members)
        self._emitted = True
        return result


class ArrayIterator(_CompositeIterator):
    """Evaluate elements in order and emit one array."""

    def __init__(self, elements: tuple[RuntimeIterator, ...]) -> None:
        super().__init__()
        self._elements = elements
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _pull(self) -> _Pull[Value | None]:
        if self._emitted:
            return None
        elements = []
        for position, operand in enumerate(self._elements, start=1):
            message = f"array element {position} must contain exactly one value"
            element = yield from _read_single_value(operand, self.context, message)
            elements.append(element)
        result = ArrayValue(elements)
        self._emitted = True
        return result


def _read_single_value(operand: RuntimeIterator, context: DynamicContext, message: str) -> _Pull[Value]:
    operand.open(context)
    try:
        value = yield operand
        if value is None or (yield operand) is not None:
            raise DynamicError(message)
        return value
    finally:
        operand.close()


class InstanceOfIterator(_CompositeIterator):
    """Test the model kind of a singleton operand and emit one boolean."""

    def __init__(self, operand: RuntimeIterator, type_name: str) -> None:
        super().__init__()
        self._operand = operand
        self._type_name = type_name
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _pull(self) -> _Pull[Value | None]:
        if self._emitted:
            return None
        value = yield from _read_single_value(
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


class ComparisonIterator(_CompositeIterator):
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

    def _read_atomic(self, operand: RuntimeIterator) -> _Pull[AtomicValue]:
        message = "comparison operands must contain exactly one atomic value"
        value = yield from _read_single_value(operand, self.context, message)
        if not isinstance(value, AtomicValue):
            raise DynamicError(message)
        return value

    def _pull(self) -> _Pull[Value | None]:
        if self._emitted:
            return None
        left = yield from self._read_atomic(self._left)
        right = yield from self._read_atomic(self._right)
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


def _read_number(iterator: RuntimeIterator, context: DynamicContext) -> _Pull[int | float]:
    message = "arithmetic operands must contain exactly one number"
    iterator.open(context)
    try:
        value = yield iterator
        if not isinstance(value, NumberValue) or (yield iterator) is not None:
            raise DynamicError(message)
        return value.value
    finally:
        iterator.close()


def _apply_arithmetic(operation, *operands: float) -> NumberValue:
    try:
        return NumberValue(operation(*operands))
    except ZeroDivisionError:
        raise DynamicError("division or remainder by zero") from None
    except (OverflowError, ValueError) as error:
        raise DynamicError("arithmetic result must be finite") from error


class ArithmeticIterator(_CompositeIterator):
    """Pull singleton numbers from child iterators and emit one result."""

    def __init__(self, operator: str, operands: tuple[RuntimeIterator, ...]) -> None:
        super().__init__()
        self._operation = _ARITHMETIC[len(operands), operator]
        self._operands = operands
        self._emitted = False

    def _restart(self) -> None:
        self._emitted = False

    def _pull(self) -> _Pull[Value | None]:
        if self._emitted:
            return None
        operands = []
        for child in self._operands:
            operands.append((yield from _read_number(child, self.context)))
        result = _apply_arithmetic(self._operation, *operands)
        self._emitted = True
        return result


class ArithmeticChainIterator(_CompositeIterator):
    """Fold a binary operator chain in source order."""

    def __init__(self, first: RuntimeIterator,
                 steps: tuple[tuple[str, RuntimeIterator], ...]) -> None:
        super().__init__()
        self._first = first
        self._steps = tuple((_ARITHMETIC[2, operator], operand) for operator, operand in steps)

    def _restart(self) -> None:
        self._emitted = False

    def _pull(self) -> _Pull[Value | None]:
        if self._emitted:
            return None
        first = yield from _read_number(self._first, self.context)
        result = NumberValue(first)
        for operation, operand in self._steps:
            right = yield from _read_number(operand, self.context)
            result = _apply_arithmetic(operation, result.value, right)
        self._emitted = True
        return result
