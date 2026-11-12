"""Checks the ``modal`` API this package calls, so the declared floor stays honest."""

import modal


def test_current_function_call_id_is_none_outside_modal() -> None:
    assert modal.current_function_call_id() is None
