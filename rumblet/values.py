"""The six value kinds from the Mini Data Model.

Payloads use the Python standard JSON decoder's representations: str, int/float,
bool, and None. Both integer and floating representations have JSON kind number.
These are model values, not Python truth values or query result sequences.
"""

from dataclasses import dataclass, field
from math import isfinite
from typing import ClassVar


class Value:
    """Model value; query truth rules belong to evaluation."""

    __slots__ = ()

    def __bool__(self) -> bool:
        raise TypeError("model values do not have implicit Python truth values")


class AtomicValue(Value):
    """Common marker for the four atomic kinds."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class StringValue(AtomicValue):
    value: str
    kind: ClassVar[str] = "string"

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise TypeError("string content must be a JSON string")
        if any(0xD800 <= ord(char) <= 0xDFFF for char in self.value):
            raise ValueError("strings must contain only Unicode scalar values")

    def __len__(self) -> int:
        return len(self.value)


@dataclass(frozen=True, slots=True)
class NumberValue(AtomicValue):
    value: int | float
    kind: ClassVar[str] = "number"

    def __post_init__(self) -> None:
        if type(self.value) not in (int, float):
            raise TypeError("number content must be a JSON number")
        if type(self.value) is float and not isfinite(self.value):
            raise ValueError("numbers must be finite")


@dataclass(frozen=True, slots=True)
class BooleanValue(AtomicValue):
    value: bool
    kind: ClassVar[str] = "boolean"

    def __post_init__(self) -> None:
        if type(self.value) is not bool:
            raise TypeError("boolean content must be a JSON boolean")


@dataclass(frozen=True, slots=True)
class NullValue(AtomicValue):
    kind: ClassVar[str] = "null"
    value: ClassVar[None] = None


NULL = NullValue()


@dataclass(frozen=True, slots=True, init=False)
class ArrayValue(Value):
    """An ordered collection of model values, separate from a query sequence."""

    _elements: tuple
    _hash: int = field(compare=False, repr=False)
    kind: ClassVar[str] = "array"

    def __init__(self, elements: list[Value]) -> None:
        if type(elements) is not list:
            raise TypeError("array elements must be supplied as a list of model values")
        for element in elements:
            _require_value(element)
        contents = tuple(elements)
        object.__setattr__(self, "_elements", contents)
        # Object members hash their values. Cache array hashes bottom-up
        # so inserting a deeply nested array does not recurse.
        object.__setattr__(self, "_hash", hash((contents,)))

    def __hash__(self) -> int:
        return self._hash

    @property
    def elements(self) -> tuple:
        """Read-only model elements; the tuple is internal storage, not a value kind."""
        return self._elements

    @property
    def value(self) -> list:
        return [element.value for element in self._elements]

    def __len__(self) -> int:
        return len(self._elements)


@dataclass(frozen=True, slots=True, init=False)
class ObjectValue(Value):
    """Unique string names mapped to model values; member order is insignificant."""

    _members: frozenset
    kind: ClassVar[str] = "object"

    def __init__(self, members: dict[str, Value] | list[tuple[str, Value]]) -> None:
        if type(members) is dict:
            pairs = members.items()
        elif type(members) is list:
            pairs = members
        else:
            raise TypeError("object members must be a dictionary or list of name/value pairs")
        collected = {}
        for name, value in pairs:
            StringValue(name)  # Names obey the same Unicode rules as string values.
            if name in collected:
                raise ValueError(f"duplicate object member name: {name!r}")
            _require_value(value)
            collected[name] = value
        object.__setattr__(self, "_members", frozenset(collected.items()))

    @property
    def members(self) -> dict[str, Value]:
        """A fresh dictionary of members; changes do not alter this object."""
        return dict(self._members)

    @property
    def value(self) -> dict:
        return {name: value.value for name, value in self._members}


def _require_value(value: Value) -> None:
    if type(value) not in (
        StringValue, NumberValue, BooleanValue, NullValue, ArrayValue, ObjectValue,
    ):
        raise TypeError("containers may contain only the six model value kinds")
