"""Built-in query functions, each taking one sequence argument."""

from itertools import islice

from rumblet.sequence import Sequence
from rumblet.values import BooleanValue, NumberValue


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


BUILTIN_FUNCTIONS = {
    "count": _count,
    "head": _head,
    "tail": _tail,
    "exists": _exists,
    "empty": _empty,
}
