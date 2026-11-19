"""Query errors defined by Mini Query Language section 4."""


class _QueryError(Exception):
    def __str__(self) -> str:
        message = super().__str__()
        name = type(self).__name__
        return f"{name}: {message}" if message else name


class StaticError(_QueryError):
    """Invalid syntax, an unbound variable, or an unknown function."""


class DynamicError(_QueryError):
    """An operation received an invalid kind or number of values."""
