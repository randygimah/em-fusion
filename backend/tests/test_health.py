"""Health endpoint tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200_with_status_body() -> None:
    # spec: api-001
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_needs_no_database() -> None:
    # spec: api-001 — it answers before persistence exists, so a call made with
    # no database configured must still succeed rather than error.
    response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_health_is_not_served_at_an_unversioned_path() -> None:
    # spec: api-001 — the failure case: serving health at /health means the
    # prefix is not owned by the backend, and the proxies would have to strip it.
    response = client.get("/health")

    assert response.status_code == 404


def test_health_answers_through_the_lifespan_context() -> None:
    # spec: api-001 — entering the app as a context manager runs the lifespan
    # startup and shutdown, which a bare TestClient call skips. This is the path
    # uvicorn actually takes, and a lifespan that raises there is invisible until
    # the container crash-loops.
    with TestClient(app) as lifespan_client:
        response = lifespan_client.get("/api/v1/health")

    assert response.status_code == 200


def test_health_route_is_tagged_system() -> None:
    # spec: api-001 — tags group the generated OpenAPI page; retro-fitting them
    # later means touching every decorator.
    schema = app.openapi()

    assert schema["paths"]["/api/v1/health"]["get"]["tags"] == ["system"]
