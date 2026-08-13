"""System health route.

Answers without touching persistence, so it stays truthful before the database
exists and does not turn a degraded database into an unreachable service.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["system"])
def get_health() -> dict[str, str]:
    """Report that the service is up. spec: api-001."""
    return {"status": "healthy"}
