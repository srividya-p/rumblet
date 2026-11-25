"""Query result sequences are lists of values, never model values themselves."""

import json
import sys
from collections.abc import Iterator
from math import copysign
from typing import TextIO

from rumblet.errors import DynamicError
from rumblet.values import ArrayValue, NumberValue, ObjectValue, Value, _require_value


class Sequence:
    """A list-backed sequence with a defensive copy at its public boundary."""

    __slots__ = ("_values",)

    def __init__(self, values: list[Value]) -> None:
        if type(values) is not list:
            raise DynamicError("a sequence requires a list of model values")
        for value in values:
            try:
                _require_value(value)
            except TypeError as error:
                raise DynamicError("a sequence may contain only model values") from error
        self._values = values.copy()

    @property
    def values(self) -> list[Value]:
        return self._values.copy()

    def __iter__(self) -> Iterator[Value]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if type(other) is not Sequence:
            return NotImplemented
        return self._values == other._values


def print_sequence(sequence: Sequence, file: TextIO | None = None) -> None:
    """Print compact JSON per value, or () for an empty sequence."""
    if type(sequence) is not Sequence:
        raise DynamicError("print_sequence requires a sequence")
    if file is None:
        file = sys.stdout
    if len(sequence) == 0:
        print("()", file=file)
        return
    try:
        lines = [
            json.dumps(_serialized_value(value), ensure_ascii=False, allow_nan=False,
                       sort_keys=True, separators=(",", ":"))
            for value in sequence
        ]
    except (ValueError, RecursionError) as error:
        raise DynamicError("result exceeds JSON serialization limits") from error
    for line in lines:
        print(line, file=file)


def _serialized_value(value: Value) -> object:
    if isinstance(value, NumberValue):
        number = value.value
        if number.is_integer() and not (number == 0 and copysign(1, number) < 0):
            return int(number)
        return number
    if isinstance(value, ArrayValue):
        return [_serialized_value(member) for member in value.elements]
    if isinstance(value, ObjectValue):
        return {name: _serialized_value(pair) for name, pair in value.members.items()}
    return value.value
