"""Built-in query functions, each taking one sequence argument."""

import json
from itertools import islice
from pathlib import Path

from rumblet.errors import DynamicError
from rumblet.sequence import Sequence
from rumblet.values import (
    NULL,
    ArrayValue,
    BooleanValue,
    NumberValue,
    ObjectValue,
    StringValue,
    Value,
)


def _count(sequence: Sequence) -> Sequence:
    return Sequence([NumberValue(len(sequence))])


def _head(sequence: Sequence) -> Sequence:
    return Sequence(list(islice(sequence, 1)))


def _tail(sequence: Sequence) -> Sequence:
    return Sequence(list(islice(sequence, 1, None)))


def _exists(sequence: Sequence) -> Sequence:
    return Sequence([BooleanValue(len(sequence) > 0)])


def _empty(sequence: Sequence) -> Sequence:
    return Sequence([BooleanValue(len(sequence) == 0)])


def _json_value(payload: object) -> Value:
    if isinstance(payload, ObjectValue):
        return payload
    if isinstance(payload, list):
        return ArrayValue([_json_value(element) for element in payload])
    if isinstance(payload, str):
        return StringValue(payload)
    if isinstance(payload, bool):
        return BooleanValue(payload)
    if payload is None:
        return NULL
    if isinstance(payload, (int, float)):
        return NumberValue(payload)
    raise ValueError("unsupported JSON value")


def _json_object(pairs: list[tuple[str, object]]) -> ObjectValue:
    return ObjectValue([(name, _json_value(value)) for name, value in pairs])


def _json_file(sequence: Sequence) -> Sequence:
    path = next(iter(sequence), None)
    if len(sequence) != 1 or not isinstance(path, StringValue):
        raise DynamicError("json_file expects a singleton string path")
    try:
        content = Path(path.value).read_bytes()
    except (OSError, ValueError) as error:
        raise DynamicError("json_file could not read the file") from error
    try:
        payload = json.loads(content.decode("utf-8"), object_pairs_hook=_json_object)
        return Sequence([_json_value(payload)])
    except (ValueError, RecursionError) as error:
        raise DynamicError("json_file requires one UTF-8 JSON value valid in the data model") from error


BUILTIN_FUNCTIONS = {
    "count": _count,
    "head": _head,
    "tail": _tail,
    "exists": _exists,
    "empty": _empty,
    "json_file": _json_file,
}
