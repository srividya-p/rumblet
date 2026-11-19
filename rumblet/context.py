"""Dynamic variable bindings shared by runtime iterators."""

from rumblet.errors import DynamicError
from rumblet.sequence import Sequence


class DynamicContext:
    """Map variable names to sequences; binding updates replace whole sequences."""

    def __init__(self, bindings: dict[str, Sequence] | None = None) -> None:
        self._bindings: dict[str, Sequence] = {}
        if bindings is not None:
            self.update(bindings)

    def update(self, bindings: dict[str, Sequence]) -> None:
        if type(bindings) is not dict:
            raise DynamicError("context bindings must be a dictionary")
        for name, sequence in bindings.items():
            if type(name) is not str or type(sequence) is not Sequence:
                raise DynamicError("context bindings require string names and sequences")
        self._bindings.update(bindings)

    def bind(self, name: str, sequence: Sequence) -> None:
        self.update({name: sequence})

    def lookup(self, name: str) -> Sequence:
        try:
            return self._bindings[name]
        except KeyError as error:
            # Static analysis will reject unbound query references before execution.
            raise DynamicError(f"missing runtime binding: {name}") from error
