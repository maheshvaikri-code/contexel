"""Typed errors (ADR-003).

Every error contexel raises on purpose is a :class:`ContexelError` carrying a
stable ``code`` -- the cross-language contract (messages are for humans and may
differ between the Python, TypeScript and C# ports; codes may not).

* :class:`ConfigError` (also a ``ValueError``): the *call* is wrong -- a bad
  option, an empty field list, an invalid regex. Always raised.
* :class:`InputShapeError` (also a ``TypeError``): the *data* is wrong -- not a
  list, an item that is not a mapping, an output field that already exists.
  Shape errors from the original stages are raised only in strict mode
  (:func:`contexel.strict`); a field conflict is always raised, because
  continuing would silently destroy data.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Optional

#: The complete, stable set of error codes.
CODES = (
    "config.invalid_value",
    "config.empty",
    "config.contradictory",
    "config.invalid_pattern",
    "input.not_list",
    "input.not_mapping",
    "input.field_conflict",
)


class ContexelError(Exception):
    """Base class: ``code`` (stable), ``stage`` and ``param`` (both optional)."""

    def __init__(self, code: str, message: str, *,
                 stage: Optional[str] = None, param: Optional[str] = None) -> None:
        if code not in CODES:
            raise ValueError(f"unknown contexel error code {code!r}")
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.param = param

    def __reduce__(self) -> Any:
        # keep the error picklable (process pools): Exception's default
        # would call cls(message) and lose the required ``code``
        return (_rebuild, (type(self), self.code, str(self), self.stage, self.param))


def _rebuild(cls: Any, code: str, message: str,
             stage: Optional[str], param: Optional[str]) -> "ContexelError":
    return cls(code, message, stage=stage, param=param)


class ConfigError(ContexelError, ValueError):
    """The stage was configured wrongly. Also a ``ValueError``."""


class InputShapeError(ContexelError, TypeError):
    """The data does not have the shape the stage needs. Also a ``TypeError``."""


def _kind(value: Any) -> str:
    return type(value).__name__


def invalid_value(stage: str, param: str, message: str) -> ConfigError:
    return ConfigError("config.invalid_value", f"{stage}: {message}",
                       stage=stage, param=param)


def check_fields(value: Any, stage: str, param: str = "fields", *,
                 allow_empty: bool = True) -> List[str]:
    """A bare string means ONE field (never its characters); otherwise a list
    or tuple of strings. ``allow_empty=False`` rejects an empty list: a stage
    that scans no fields silently does nothing, and for a security control
    that is the failure to refuse."""
    if isinstance(value, str):
        names = [value]
    elif isinstance(value, (list, tuple)):
        if not all(isinstance(v, str) for v in value):
            raise invalid_value(stage, param,
                                f"{param} must contain only strings")
        names = list(value)
    else:
        raise invalid_value(
            stage, param,
            f"{param} must be a string or a list of strings, got {_kind(value)}")
    if not names and not allow_empty:
        raise ConfigError(
            "config.empty",
            f"{stage}: {param} is empty, so the stage would silently do "
            f"nothing; pass at least one field", stage=stage, param=param)
    return names


def check_query(value: Any, stage: str, param: str = "query") -> Any:
    if isinstance(value, str) or isinstance(value, (list, tuple)):
        return value
    raise invalid_value(
        stage, param,
        f"{param} must be a string or a list of strings, got {_kind(value)}")


def check_non_negative_int(value: Any, stage: str, param: str) -> int:
    """An integer >= 0. A bool is not an integer here (``True`` would pass
    for 1), and ``0`` stays valid: "no budget left" is a real answer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise invalid_value(stage, param,
                            f"{param} must be an integer >= 0, got {value!r}")
    return value


def check_bool(value: Any, stage: str, param: str) -> bool:
    if not isinstance(value, bool):
        raise invalid_value(stage, param,
                            f"{param} must be True or False, got {value!r}")
    return value


def check_str(value: Any, stage: str, param: str) -> str:
    if not isinstance(value, str):
        raise invalid_value(stage, param,
                            f"{param} must be a string, got {_kind(value)}")
    return value


def check_choice(value: Any, stage: str, param: str,
                 choices: Iterable[str]) -> str:
    options = tuple(choices)
    if not isinstance(value, str) or value not in options:
        listed = ", ".join(repr(c) for c in options)
        raise invalid_value(stage, param,
                            f"{param} must be one of {listed}, got {value!r}")
    return value
