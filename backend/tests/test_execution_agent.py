from app.agents.execution.execution_agent import _finalise_results


def test_finalise_results_converts_stack_trace_list_to_text():
    state = {
        "test_cases": [],
        "environment": "staging",
        "suite_name": "Suite",
        "results": [
            {
                "test_case_id": "TC-0001",
                "test_name": "Example failure",
                "status": "failed",
                "duration_ms": 2500,
                "error_message": ["AssertionError", "Expected true"],
                "stack_trace": ["line 1", "line 2"],
                "logs": "single log line",
            }
        ],
        "errors": [],
    }

    finalised = _finalise_results(state)
    result = finalised["results"][0]

    assert result["error_message"] == "AssertionError\nExpected true"
    assert result["stack_trace"] == "line 1\nline 2"
    assert result["logs"] == ["single log line"]
