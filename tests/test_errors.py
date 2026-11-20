"""The typed error model (ADR-003, brief AC 6): a stable ``code`` is the
cross-language contract, the two subclasses keep every existing ``except``
clause working, and the original quarantine messages are untouched."""
import pickle

import pytest

import contexel
from contexel import ConfigError, ContexelError, InputShapeError, errors

DOCUMENTED_CODES = (
    "config.invalid_value", "config.empty", "config.contradictory",
    "config.invalid_pattern", "input.not_list", "input.not_mapping",
    "input.field_conflict",
)


def test_config_error_is_a_valueerror_and_a_contexel_error():
    e = ConfigError("config.empty", "nothing to do", stage="quarantine", param="fields")
    assert isinstance(e, ContexelError)
    assert isinstance(e, ValueError)
    assert not isinstance(e, TypeError)
    assert (e.code, e.stage, e.param, str(e)) == (
        "config.empty", "quarantine", "fields", "nothing to do")


def test_input_shape_error_is_a_typeerror_and_a_contexel_error():
    e = InputShapeError("input.not_list", "not a list", stage="select")
    assert isinstance(e, ContexelError)
    assert isinstance(e, TypeError)
    assert not isinstance(e, ValueError)
    assert (e.code, e.stage, e.param) == ("input.not_list", "select", None)


def test_error_codes_are_the_documented_set():
    assert errors.CODES == DOCUMENTED_CODES


def test_an_unknown_code_is_refused():
    with pytest.raises(ValueError, match="unknown contexel error code"):
        ConfigError("config.made_up", "x")


@pytest.mark.parametrize("err", [
    ConfigError("config.invalid_value", "bad", stage="rescore", param="match"),
    InputShapeError("input.field_conflict", "clash", stage="quarantine", param="into"),
])
def test_errors_survive_pickling_with_every_field(err):
    back = pickle.loads(pickle.dumps(err))
    assert type(back) is type(err)
    assert (back.code, back.stage, back.param, str(back)) == (
        err.code, err.stage, err.param, str(err))


def test_the_errors_are_exported_from_the_package():
    for name in ("ContexelError", "ConfigError", "InputShapeError", "strict"):
        assert name in contexel.__all__ and hasattr(contexel, name)
