import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.requirement import RequirementCreate


@pytest.mark.parametrize("source", ["pasted_text", "api_specification"])
def test_manual_intake_source_types_are_accepted(source: str):
    requirement = RequirementCreate(
        project_id=7,
        title="Governed intake source",
        summary="Original source content",
        source=source,
    )

    assert requirement.source == source


def test_unknown_intake_source_type_is_rejected():
    with pytest.raises(ValidationError):
        RequirementCreate(
            project_id=7,
            title="Unsupported source",
            source="unsupported",
        )


@pytest.mark.parametrize(
    "path",
    ["/api/v1/requirements", "/api/v1/requirements/"],
)
def test_requirement_create_route_does_not_redirect(path: str):
    response = TestClient(app, follow_redirects=False).post(
        path,
        json={
            "project_id": 7,
            "title": "Governed intake source",
            "summary": "Original source content",
            "source": "pasted_text",
        },
    )

    assert response.status_code == 401
    assert "location" not in response.headers
