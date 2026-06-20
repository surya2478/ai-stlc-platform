from types import SimpleNamespace

from app.services.agent_run_service import _normalise_log, _result_output


def test_normalise_log_accepts_strings_and_dicts():
    assert _normalise_log("plain message") == {
        "level": "info",
        "step": None,
        "message": "plain message",
        "data": None,
    }

    assert _normalise_log(
        {"level": "WARN", "step": "parse", "message": "fixed", "data": ["a", "b"]}
    ) == {
        "level": "warning",
        "step": "parse",
        "message": "fixed",
        "data": {"value": ["a", "b"]},
    }


def test_result_output_supports_custom_and_base_agent_shapes():
    custom_result = SimpleNamespace(data={"items": [1, 2]})
    base_result = SimpleNamespace(output={"items": [3]})

    assert _result_output(custom_result) == {"items": [1, 2]}
    assert _result_output(base_result) == {"items": [3]}
